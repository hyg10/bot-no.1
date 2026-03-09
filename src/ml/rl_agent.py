"""
Reinforcement Learning Trading Agent
PPO (Proximal Policy Optimization) based agent for trading decisions.

State Space: Market features (price, volume, indicators, portfolio state)
Action Space: [Hold, Buy Small, Buy Medium, Buy Large, Sell Small, Sell Medium, Sell Large]
Reward: Risk-adjusted return (Sharpe-based)
"""
import numpy as np
import json
import os
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
import random


@dataclass
class RLConfig:
    """Configuration for RL Agent"""
    state_size: int = 20           # Number of state features
    action_size: int = 7           # Number of possible actions
    learning_rate: float = 0.001
    gamma: float = 0.95            # Discount factor
    epsilon: float = 1.0           # Exploration rate (starts at 100%)
    epsilon_min: float = 0.05      # Minimum exploration rate
    epsilon_decay: float = 0.995   # Exploration decay per episode
    batch_size: int = 64
    memory_size: int = 10000
    target_update_freq: int = 100  # Steps between target network updates
    hidden_size: int = 128


class SimpleNeuralNet:
    """
    Simple neural network implemented with numpy only (no heavy ML framework).
    Architecture: Input -> Hidden1 -> Hidden2 -> Output
    Uses ReLU activation and He initialization.
    """

    def __init__(self, input_size: int, hidden_size: int, output_size: int, lr: float = 0.001):
        self.lr = lr
        # He initialization for ReLU
        self.W1 = np.random.randn(input_size, hidden_size) * np.sqrt(2.0 / input_size)
        self.b1 = np.zeros((1, hidden_size))
        self.W2 = np.random.randn(hidden_size, hidden_size) * np.sqrt(2.0 / hidden_size)
        self.b2 = np.zeros((1, hidden_size))
        self.W3 = np.random.randn(hidden_size, output_size) * np.sqrt(2.0 / hidden_size)
        self.b3 = np.zeros((1, output_size))

        # Adam optimizer parameters
        self.m = [np.zeros_like(w) for w in [self.W1, self.b1, self.W2, self.b2, self.W3, self.b3]]
        self.v = [np.zeros_like(w) for w in [self.W1, self.b1, self.W2, self.b2, self.W3, self.b3]]
        self.t = 0
        self.beta1, self.beta2 = 0.9, 0.999
        self.eps_adam = 1e-8

    def relu(self, x):
        return np.maximum(0, x)

    def relu_grad(self, x):
        return (x > 0).astype(float)

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Forward pass"""
        self._z1 = x @ self.W1 + self.b1
        self._a1 = self.relu(self._z1)
        self._z2 = self._a1 @ self.W2 + self.b2
        self._a2 = self.relu(self._z2)
        self._z3 = self._a2 @ self.W3 + self.b3
        return self._z3  # Q-values (no activation for output)

    def backward(self, x: np.ndarray, targets: np.ndarray, mask: np.ndarray) -> float:
        """Backward pass - only update Q-values for taken actions (mask)"""
        # Forward pass to get predictions
        preds = self.forward(x)

        # Loss: MSE only on masked (taken) actions
        diff = (preds - targets) * mask
        loss = np.mean(diff ** 2)

        # Backprop
        d_out = 2 * diff / (mask.sum() + 1e-8)

        dW3 = self._a2.T @ d_out
        db3 = d_out.sum(axis=0, keepdims=True)
        d_a2 = d_out @ self.W3.T

        d_z2 = d_a2 * self.relu_grad(self._z2)
        dW2 = self._a1.T @ d_z2
        db2 = d_z2.sum(axis=0, keepdims=True)
        d_a1 = d_z2 @ self.W2.T

        d_z1 = d_a1 * self.relu_grad(self._z1)
        dW1 = x.T @ d_z1
        db1 = d_z1.sum(axis=0, keepdims=True)

        grads = [dW1, db1, dW2, db2, dW3, db3]
        weights = [self.W1, self.b1, self.W2, self.b2, self.W3, self.b3]

        # Adam update
        self.t += 1
        for i, (w, g) in enumerate(zip(weights, grads)):
            self.m[i] = self.beta1 * self.m[i] + (1 - self.beta1) * g
            self.v[i] = self.beta2 * self.v[i] + (1 - self.beta2) * g**2
            m_hat = self.m[i] / (1 - self.beta1**self.t)
            v_hat = self.v[i] / (1 - self.beta2**self.t)
            w -= self.lr * m_hat / (np.sqrt(v_hat) + self.eps_adam)

        return float(loss)

    def copy_weights_from(self, other: 'SimpleNeuralNet'):
        """Copy weights from another network (for target network)"""
        self.W1 = other.W1.copy()
        self.b1 = other.b1.copy()
        self.W2 = other.W2.copy()
        self.b2 = other.b2.copy()
        self.W3 = other.W3.copy()
        self.b3 = other.b3.copy()

    def save(self, path: str):
        """Save weights to file"""
        np.savez(path,
                 W1=self.W1, b1=self.b1,
                 W2=self.W2, b2=self.b2,
                 W3=self.W3, b3=self.b3)

    def load(self, path: str):
        """Load weights from file"""
        data = np.load(path + '.npz')
        self.W1 = data['W1']
        self.b1 = data['b1']
        self.W2 = data['W2']
        self.b2 = data['b2']
        self.W3 = data['W3']
        self.b3 = data['b3']


class TradingRLAgent:
    """
    Deep Q-Network (DQN) agent for trading.

    Actions:
      0: Hold
      1: Buy 10% of capital
      2: Buy 20% of capital
      3: Buy 30% of capital
      4: Sell 10% of position
      5: Sell 50% of position
      6: Sell 100% of position (close all)

    State features (20):
      0-4:   Normalized returns (last 5 bars)
      5-9:   Volume ratios (last 5 bars vs 20-bar avg)
      10:    RSI (0-1 normalized)
      11:    MACD signal (normalized)
      12:    BB position (price within Bollinger Bands)
      13:    Portfolio cash ratio
      14:    Portfolio position ratio
      15:    Unrealized PnL %
      16:    Time of day (0-1 normalized)
      17:    Volatility (recent vs long-term)
      18:    Trend strength (EMA ratio)
      19:    Market momentum (ROC)
    """

    ACTION_NAMES = [
        "Hold",
        "Buy 10%", "Buy 20%", "Buy 30%",
        "Sell 10%", "Sell 50%", "Sell 100%"
    ]
    BUY_SIZES = [0, 0.10, 0.20, 0.30, 0, 0, 0]
    SELL_SIZES = [0, 0, 0, 0, 0.10, 0.50, 1.00]

    def __init__(self, config: RLConfig = None, model_dir: str = "models/rl"):
        self.config = config or RLConfig()
        self.model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)

        # Q-networks (online + target)
        self.online_net = SimpleNeuralNet(
            self.config.state_size,
            self.config.hidden_size,
            self.config.action_size,
            self.config.learning_rate
        )
        self.target_net = SimpleNeuralNet(
            self.config.state_size,
            self.config.hidden_size,
            self.config.action_size,
            self.config.learning_rate
        )
        self.target_net.copy_weights_from(self.online_net)

        # Experience replay
        self.memory: deque = deque(maxlen=self.config.memory_size)

        # Training state
        self.epsilon = self.config.epsilon
        self.steps = 0
        self.episodes = 0
        self.losses: List[float] = []

        # Performance tracking
        self.episode_rewards: List[float] = []
        self.action_counts = np.zeros(self.config.action_size)

    def select_action(self, state: np.ndarray, training: bool = True) -> int:
        """
        Epsilon-greedy action selection.
        In training: explores randomly with probability epsilon.
        In inference: always picks best action.
        """
        if training and random.random() < self.epsilon:
            action = random.randint(0, self.config.action_size - 1)
        else:
            q_values = self.online_net.forward(state.reshape(1, -1))
            action = int(np.argmax(q_values[0]))

        self.action_counts[action] += 1
        return action

    def store_experience(self, state: np.ndarray, action: int, reward: float,
                         next_state: np.ndarray, done: bool):
        """Store experience in replay buffer"""
        self.memory.append((state.copy(), action, reward, next_state.copy(), done))

    def train_step(self) -> Optional[float]:
        """Sample batch and update Q-network"""
        if len(self.memory) < self.config.batch_size:
            return None

        batch = random.sample(self.memory, self.config.batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)

        states_arr = np.array(states)
        next_states_arr = np.array(next_states)
        rewards_arr = np.array(rewards)
        dones_arr = np.array(dones, dtype=float)
        actions_arr = np.array(actions)

        # Current Q-values
        current_q = self.online_net.forward(states_arr)

        # Target Q-values (Double DQN)
        next_q_online = self.online_net.forward(next_states_arr)
        next_q_target = self.target_net.forward(next_states_arr)
        best_actions = np.argmax(next_q_online, axis=1)
        next_q_values = next_q_target[np.arange(self.config.batch_size), best_actions]

        # Bellman update
        targets = current_q.copy()
        for i in range(self.config.batch_size):
            targets[i, actions_arr[i]] = (
                rewards_arr[i] + self.config.gamma * next_q_values[i] * (1 - dones_arr[i])
            )

        # Mask: only update Q-values for taken actions
        mask = np.zeros_like(current_q)
        mask[np.arange(self.config.batch_size), actions_arr] = 1.0

        loss = self.online_net.backward(states_arr, targets, mask)
        self.losses.append(loss)

        # Update epsilon
        if self.epsilon > self.config.epsilon_min:
            self.epsilon *= self.config.epsilon_decay

        # Update target network
        self.steps += 1
        if self.steps % self.config.target_update_freq == 0:
            self.target_net.copy_weights_from(self.online_net)

        return loss

    def get_stats(self) -> Dict:
        """Return training statistics"""
        total_actions = self.action_counts.sum()
        action_dist = {}
        for i, name in enumerate(self.ACTION_NAMES):
            pct = (self.action_counts[i] / total_actions * 100) if total_actions > 0 else 0
            action_dist[name] = f"{pct:.1f}%"

        return {
            "epsilon": round(self.epsilon, 4),
            "memory_size": len(self.memory),
            "steps": self.steps,
            "episodes": self.episodes,
            "avg_loss": round(np.mean(self.losses[-100:]), 6) if self.losses else 0,
            "action_distribution": action_dist
        }

    def save(self, suffix: str = ""):
        """Save model weights and metadata"""
        name = f"rl_agent{suffix}"
        self.online_net.save(os.path.join(self.model_dir, name))
        meta = {
            "epsilon": self.epsilon,
            "steps": self.steps,
            "episodes": self.episodes,
            "losses_tail": self.losses[-50:],
            "action_counts": self.action_counts.tolist(),
            "saved_at": datetime.now().isoformat()
        }
        with open(os.path.join(self.model_dir, f"{name}_meta.json"), "w") as f:
            json.dump(meta, f, indent=2)
        print(f"[RL Agent] Model saved: {name}")

    def load(self, suffix: str = ""):
        """Load model weights and metadata"""
        name = f"rl_agent{suffix}"
        weights_path = os.path.join(self.model_dir, name)
        meta_path = os.path.join(self.model_dir, f"{name}_meta.json")

        if not os.path.exists(weights_path + '.npz'):
            print(f"[RL Agent] No saved model found at {weights_path}. Starting fresh.")
            return False

        self.online_net.load(weights_path)
        self.target_net.copy_weights_from(self.online_net)

        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            self.epsilon = meta.get("epsilon", self.config.epsilon)
            self.steps = meta.get("steps", 0)
            self.episodes = meta.get("episodes", 0)
            self.losses = meta.get("losses_tail", [])
            self.action_counts = np.array(meta.get("action_counts",
                                                    [0] * self.config.action_size))
            print(f"[RL Agent] Model loaded (epsilon={self.epsilon:.3f}, steps={self.steps})")

        return True


class MarketStateBuilder:
    """
    Builds normalized state vector from market data.
    Designed to work with OHLCV data and portfolio state.
    """

    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        self.price_history: deque = deque(maxlen=lookback + 10)
        self.volume_history: deque = deque(maxlen=lookback + 10)

    def update(self, price: float, volume: float = 1.0):
        """Add new price/volume data point"""
        self.price_history.append(price)
        self.volume_history.append(volume)

    def build_state(self, portfolio_cash: float, portfolio_value: float,
                    position_size: float = 0.0, entry_price: float = 0.0) -> Optional[np.ndarray]:
        """
        Build a 20-feature state vector.
        Returns None if not enough data.
        """
        if len(self.price_history) < self.lookback:
            return None

        prices = np.array(list(self.price_history))
        volumes = np.array(list(self.volume_history))
        current_price = prices[-1]

        state = np.zeros(20)

        # Features 0-4: Normalized returns (last 5 bars)
        returns = np.diff(prices[-6:]) / prices[-6:-1]
        state[0:5] = np.clip(returns, -0.1, 0.1) / 0.1  # Normalize to [-1, 1]

        # Features 5-9: Volume ratio vs 20-bar average
        vol_avg = np.mean(volumes[:-5]) if len(volumes) > 5 else 1.0
        vol_recent = volumes[-5:]
        state[5:10] = np.clip(vol_recent / (vol_avg + 1e-8), 0, 5) / 5

        # Feature 10: RSI (14-period)
        state[10] = self._rsi(prices[-15:]) / 100.0

        # Feature 11: MACD signal (normalized)
        state[11] = self._macd_signal(prices)

        # Feature 12: Bollinger Band position
        state[12] = self._bb_position(prices[-20:], current_price)

        # Feature 13: Cash ratio
        total = portfolio_cash + portfolio_value
        state[13] = portfolio_cash / total if total > 0 else 1.0

        # Feature 14: Position ratio
        state[14] = portfolio_value / total if total > 0 else 0.0

        # Feature 15: Unrealized PnL %
        if position_size > 0 and entry_price > 0:
            unrealized_pnl_pct = (current_price - entry_price) / entry_price
            state[15] = np.clip(unrealized_pnl_pct, -0.5, 0.5) / 0.5
        else:
            state[15] = 0.0

        # Feature 16: Time of day
        hour = datetime.now().hour
        state[16] = hour / 23.0

        # Feature 17: Recent vs long-term volatility
        vol_short = np.std(returns[-5:]) if len(returns) >= 5 else 0
        vol_long = np.std(np.diff(prices) / prices[:-1]) if len(prices) > 2 else 0.001
        state[17] = np.clip(vol_short / (vol_long + 1e-8), 0, 5) / 5

        # Feature 18: Trend strength (EMA ratio)
        ema_short = self._ema(prices, 5)
        ema_long = self._ema(prices, 20)
        trend = (ema_short - ema_long) / (ema_long + 1e-8)
        state[18] = np.clip(trend, -0.05, 0.05) / 0.05

        # Feature 19: Momentum (Rate of Change)
        roc = (current_price - prices[-10]) / (prices[-10] + 1e-8) if len(prices) >= 10 else 0
        state[19] = np.clip(roc, -0.1, 0.1) / 0.1

        return state.astype(np.float32)

    def _rsi(self, prices: np.ndarray, period: int = 14) -> float:
        """Relative Strength Index"""
        if len(prices) < period + 1:
            return 50.0
        deltas = np.diff(prices)
        gains = np.maximum(deltas, 0)
        losses = np.maximum(-deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _macd_signal(self, prices: np.ndarray) -> float:
        """MACD signal normalized to [-1, 1]"""
        if len(prices) < 26:
            return 0.0
        ema12 = self._ema(prices, 12)
        ema26 = self._ema(prices, 26)
        macd = ema12 - ema26
        signal = macd / (prices[-1] + 1e-8)  # Normalize by price
        return float(np.clip(signal * 100, -1, 1))

    def _bb_position(self, prices: np.ndarray, current: float) -> float:
        """Position within Bollinger Bands: 0 = lower band, 0.5 = middle, 1 = upper band"""
        if len(prices) < 2:
            return 0.5
        mean = np.mean(prices)
        std = np.std(prices)
        if std == 0:
            return 0.5
        upper = mean + 2 * std
        lower = mean - 2 * std
        pos = (current - lower) / (upper - lower)
        return float(np.clip(pos, 0, 1))

    def _ema(self, prices: np.ndarray, period: int) -> float:
        """Exponential Moving Average"""
        if len(prices) == 0:
            return 0.0
        if len(prices) < period:
            return float(np.mean(prices))
        k = 2.0 / (period + 1)
        ema = prices[-period]
        for price in prices[-period + 1:]:
            ema = price * k + ema * (1 - k)
        return float(ema)

    def ready(self) -> bool:
        """Check if enough data has been collected"""
        return len(self.price_history) >= self.lookback
