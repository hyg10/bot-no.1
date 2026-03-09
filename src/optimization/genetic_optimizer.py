"""
Genetic Algorithm Optimizer for Strategy Parameters
"""
import random
import numpy as np
from typing import List, Dict, Tuple, Callable
from dataclasses import dataclass
from deap import base, creator, tools, algorithms


@dataclass
class ParameterRange:
    """Parameter range for optimization"""
    name: str
    min_value: float
    max_value: float
    step: float = None
    is_integer: bool = False


@dataclass
class OptimizationResult:
    """Optimization result"""
    best_params: Dict[str, float]
    best_fitness: float
    generation: int
    all_results: List[Tuple[Dict, float]]


class GeneticOptimizer:
    """
    Genetic Algorithm for optimizing strategy parameters
    """
    
    def __init__(
        self,
        parameter_ranges: List[ParameterRange],
        fitness_function: Callable,
        population_size: int = 20,
        generations: int = 50,
        crossover_prob: float = 0.7,
        mutation_prob: float = 0.2,
        tournament_size: int = 3
    ):
        """
        Initialize Genetic Algorithm Optimizer
        
        Args:
            parameter_ranges: List of parameters to optimize
            fitness_function: Function that takes params dict and returns fitness score
            population_size: Size of population in each generation
            generations: Number of generations to evolve
            crossover_prob: Probability of crossover
            mutation_prob: Probability of mutation
            tournament_size: Size of tournament for selection
        """
        self.parameter_ranges = parameter_ranges
        self.fitness_function = fitness_function
        self.population_size = population_size
        self.generations = generations
        self.crossover_prob = crossover_prob
        self.mutation_prob = mutation_prob
        self.tournament_size = tournament_size
        
        self._setup_deap()
    
    def _setup_deap(self):
        """Setup DEAP framework"""
        # Create fitness and individual classes
        if not hasattr(creator, "FitnessMax"):
            creator.create("FitnessMax", base.Fitness, weights=(1.0,))
        if not hasattr(creator, "Individual"):
            creator.create("Individual", list, fitness=creator.FitnessMax)
        
        self.toolbox = base.Toolbox()
        
        # Register parameter generators
        for i, param in enumerate(self.parameter_ranges):
            if param.is_integer:
                self.toolbox.register(
                    f"attr_{i}",
                    random.randint,
                    int(param.min_value),
                    int(param.max_value)
                )
            else:
                self.toolbox.register(
                    f"attr_{i}",
                    random.uniform,
                    param.min_value,
                    param.max_value
                )
        
        # Register individual and population
        attr_list = [getattr(self.toolbox, f"attr_{i}") for i in range(len(self.parameter_ranges))]
        self.toolbox.register("individual", tools.initCycle, creator.Individual, tuple(attr_list), n=1)
        self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)
        
        # Register genetic operators
        self.toolbox.register("evaluate", self._evaluate)
        self.toolbox.register("mate", tools.cxTwoPoint)
        self.toolbox.register("mutate", self._mutate)
        self.toolbox.register("select", tools.selTournament, tournsize=self.tournament_size)
    
    def _params_to_dict(self, individual: List[float]) -> Dict[str, float]:
        """Convert individual to parameter dictionary"""
        params = {}
        for i, param in enumerate(self.parameter_ranges):
            value = individual[i]
            if param.is_integer:
                value = int(value)
            elif param.step:
                value = round(value / param.step) * param.step
            params[param.name] = value
        return params
    
    def _evaluate(self, individual: List[float]) -> Tuple[float,]:
        """Evaluate fitness of an individual"""
        params = self._params_to_dict(individual)
        fitness = self.fitness_function(params)
        return (fitness,)
    
    def _mutate(self, individual: List[float]) -> Tuple[List[float],]:
        """Mutate an individual"""
        for i, param in enumerate(self.parameter_ranges):
            if random.random() < self.mutation_prob:
                if param.is_integer:
                    individual[i] = random.randint(int(param.min_value), int(param.max_value))
                else:
                    # Gaussian mutation
                    mu = individual[i]
                    sigma = (param.max_value - param.min_value) * 0.1
                    individual[i] = np.clip(
                        random.gauss(mu, sigma),
                        param.min_value,
                        param.max_value
                    )
        return (individual,)
    
    def optimize(self, verbose: bool = True) -> OptimizationResult:
        """
        Run genetic algorithm optimization
        
        Returns:
            OptimizationResult with best parameters and fitness
        """
        if verbose:
            print("\n" + "="*60)
            print("GENETIC ALGORITHM OPTIMIZATION")
            print("="*60)
            print(f"\nPopulation Size: {self.population_size}")
            print(f"Generations: {self.generations}")
            print(f"Crossover Probability: {self.crossover_prob}")
            print(f"Mutation Probability: {self.mutation_prob}")
            print("\nOptimizing parameters:")
            for param in self.parameter_ranges:
                print(f"  {param.name}: [{param.min_value}, {param.max_value}]")
            print()
        
        # Initialize population
        population = self.toolbox.population(n=self.population_size)
        
        # Statistics
        stats = tools.Statistics(lambda ind: ind.fitness.values)
        stats.register("avg", np.mean)
        stats.register("std", np.std)
        stats.register("min", np.min)
        stats.register("max", np.max)
        
        # Hall of fame
        hof = tools.HallOfFame(1)
        
        # Run evolution
        population, logbook = algorithms.eaSimple(
            population,
            self.toolbox,
            cxpb=self.crossover_prob,
            mutpb=self.mutation_prob,
            ngen=self.generations,
            stats=stats,
            halloffame=hof,
            verbose=verbose
        )
        
        # Get best individual
        best_individual = hof[0]
        best_params = self._params_to_dict(best_individual)
        best_fitness = best_individual.fitness.values[0]
        
        # Collect all results
        all_results = []
        for ind in population:
            params = self._params_to_dict(ind)
            fitness = ind.fitness.values[0]
            all_results.append((params, fitness))
        
        result = OptimizationResult(
            best_params=best_params,
            best_fitness=best_fitness,
            generation=self.generations,
            all_results=all_results
        )
        
        if verbose:
            print("\n" + "="*60)
            print("OPTIMIZATION COMPLETE")
            print("="*60)
            print(f"\n🏆 Best Fitness: {best_fitness:.4f}")
            print("\n📊 Best Parameters:")
            for param_name, param_value in best_params.items():
                print(f"  {param_name}: {param_value}")
            print("\n" + "="*60 + "\n")
        
        return result


class GridSearchOptimizer:
    """
    Grid Search optimizer (exhaustive search)
    """
    
    def __init__(
        self,
        parameter_ranges: List[ParameterRange],
        fitness_function: Callable
    ):
        self.parameter_ranges = parameter_ranges
        self.fitness_function = fitness_function
    
    def _generate_grid(self) -> List[Dict[str, float]]:
        """Generate all parameter combinations"""
        import itertools
        
        param_values = []
        for param in self.parameter_ranges:
            if param.is_integer:
                values = list(range(int(param.min_value), int(param.max_value) + 1))
            elif param.step:
                values = np.arange(param.min_value, param.max_value + param.step, param.step)
            else:
                values = np.linspace(param.min_value, param.max_value, 10)
            param_values.append(values)
        
        # Generate all combinations
        combinations = list(itertools.product(*param_values))
        
        # Convert to dict format
        param_dicts = []
        for combo in combinations:
            params = {
                param.name: value
                for param, value in zip(self.parameter_ranges, combo)
            }
            param_dicts.append(params)
        
        return param_dicts
    
    def optimize(self, verbose: bool = True) -> OptimizationResult:
        """Run grid search optimization"""
        if verbose:
            print("\n" + "="*60)
            print("GRID SEARCH OPTIMIZATION")
            print("="*60)
        
        param_grid = self._generate_grid()
        total_combinations = len(param_grid)
        
        if verbose:
            print(f"\nTotal Combinations: {total_combinations}")
            print("\nOptimizing...\n")
        
        best_params = None
        best_fitness = float('-inf')
        all_results = []
        
        for i, params in enumerate(param_grid):
            fitness = self.fitness_function(params)
            all_results.append((params, fitness))
            
            if fitness > best_fitness:
                best_fitness = fitness
                best_params = params
            
            if verbose and (i + 1) % max(1, total_combinations // 10) == 0:
                print(f"Progress: {i + 1}/{total_combinations} ({(i+1)/total_combinations*100:.1f}%)")
        
        result = OptimizationResult(
            best_params=best_params,
            best_fitness=best_fitness,
            generation=1,
            all_results=all_results
        )
        
        if verbose:
            print("\n" + "="*60)
            print("OPTIMIZATION COMPLETE")
            print("="*60)
            print(f"\n🏆 Best Fitness: {best_fitness:.4f}")
            print("\n📊 Best Parameters:")
            for param_name, param_value in best_params.items():
                print(f"  {param_name}: {param_value}")
            print("\n" + "="*60 + "\n")
        
        return result
