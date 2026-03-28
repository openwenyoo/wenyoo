"""Numerical Design System - Economy balance, difficulty curves, and reward suggestions.

This module provides tools for analyzing and managing the numerical aspects of
story games, including:
- Economy flow analysis (income vs expenses)
- Difficulty curve management
- Reward/cost suggestions based on balance
- Sustainability calculations
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class BalanceStatus(str, Enum):
    """Status of economy balance."""
    SURPLUS = "surplus"  # Player gains resources over time
    BALANCED = "balanced"  # Roughly equal in/out
    DEFICIT = "deficit"  # Player loses resources over time
    CRITICAL = "critical"  # Severe imbalance


class DifficultyLevel(str, Enum):
    """Difficulty levels for checks."""
    TRIVIAL = "trivial"
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
    VERY_HARD = "very_hard"


@dataclass
class IncomeSource:
    """An action that provides resources."""
    action_id: str
    node_id: str
    currency: str
    min_value: int
    max_value: int
    frequency: str = "per_action"  # per_action, per_day, per_week
    conditions: List[str] = field(default_factory=list)
    
    @property
    def expected_value(self) -> float:
        """Expected value per occurrence."""
        return (self.min_value + self.max_value) / 2


@dataclass
class ExpenseSink:
    """An action that consumes resources."""
    action_id: str
    node_id: str
    currency: str
    min_value: int
    max_value: int
    frequency: str = "per_action"
    is_optional: bool = True
    
    @property
    def expected_value(self) -> float:
        """Expected cost per occurrence."""
        return (self.min_value + self.max_value) / 2


@dataclass
class StatCheck:
    """A stat check in the game."""
    action_id: str
    node_id: str
    attribute: str
    threshold: int
    difficulty: DifficultyLevel = DifficultyLevel.NORMAL
    success_reward: Optional[Dict[str, int]] = None
    failure_penalty: Optional[Dict[str, int]] = None


@dataclass
class BalanceReport:
    """Report on economy balance."""
    currency: str
    income_per_period: float
    expense_per_period: float
    net_flow: float
    status: BalanceStatus
    sustainability_periods: int  # How many periods until resources depleted
    recommendations: List[str] = field(default_factory=list)
    income_breakdown: Dict[str, float] = field(default_factory=dict)
    expense_breakdown: Dict[str, float] = field(default_factory=dict)


@dataclass
class DifficultyReport:
    """Report on difficulty curve."""
    period: str
    average_threshold: float
    pass_rate_estimate: float  # Estimated with default stats
    hardest_checks: List[Tuple[str, int]]  # (action_id, threshold)
    easiest_checks: List[Tuple[str, int]]
    recommendations: List[str] = field(default_factory=list)


class NumericalDesign:
    """Manages numerical balance for a story.
    
    Tracks income sources, expense sinks, and stat checks to provide
    balance analysis and suggestions.
    """
    
    def __init__(self):
        """Initialize the numerical design tracker."""
        self.income_sources: Dict[str, IncomeSource] = {}
        self.expense_sinks: Dict[str, ExpenseSink] = {}
        self.stat_checks: Dict[str, StatCheck] = {}
        
        # Currency configurations
        self.currency_configs: Dict[str, Dict[str, Any]] = {}
        
        # Attribute configurations
        self.attribute_configs: Dict[str, Dict[str, Any]] = {}
        
        # Difficulty settings by period
        self.difficulty_settings: Dict[str, Dict[str, int]] = {
            "early": {"easy": 30, "normal": 40, "hard": 55},
            "mid": {"easy": 35, "normal": 45, "hard": 60},
            "late": {"easy": 40, "normal": 50, "hard": 65}
        }
    
    def add_income_source(self, source: IncomeSource):
        """Register an income source."""
        key = f"{source.node_id}:{source.action_id}"
        self.income_sources[key] = source
        logger.debug(f"Added income source: {key} ({source.currency}: {source.min_value}-{source.max_value})")
    
    def add_expense_sink(self, sink: ExpenseSink):
        """Register an expense sink."""
        key = f"{sink.node_id}:{sink.action_id}"
        self.expense_sinks[key] = sink
        logger.debug(f"Added expense sink: {key} ({sink.currency}: {sink.min_value}-{sink.max_value})")
    
    def add_stat_check(self, check: StatCheck):
        """Register a stat check."""
        key = f"{check.node_id}:{check.action_id}"
        self.stat_checks[key] = check
        logger.debug(f"Added stat check: {key} ({check.attribute} >= {check.threshold})")
    
    def configure_currency(
        self,
        currency_id: str,
        initial_value: int,
        critical_threshold: int = 0,
        target_flow: str = "balanced"
    ):
        """Configure a currency."""
        self.currency_configs[currency_id] = {
            "initial": initial_value,
            "critical": critical_threshold,
            "target_flow": target_flow
        }
    
    def configure_attribute(
        self,
        attribute_id: str,
        initial_value: int = 50,
        min_value: int = 0,
        max_value: int = 100
    ):
        """Configure an attribute."""
        self.attribute_configs[attribute_id] = {
            "initial": initial_value,
            "min": min_value,
            "max": max_value
        }
    
    def analyze_balance(self, currency: str, period: str = "per_week") -> BalanceReport:
        """Analyze the balance for a specific currency.
        
        Args:
            currency: The currency to analyze
            period: Time period for analysis
            
        Returns:
            BalanceReport with analysis results
        """
        # Calculate total income
        income_breakdown = {}
        total_income = 0.0
        for key, source in self.income_sources.items():
            if source.currency == currency:
                income_breakdown[key] = source.expected_value
                total_income += source.expected_value
        
        # Calculate total expenses
        expense_breakdown = {}
        total_expense = 0.0
        for key, sink in self.expense_sinks.items():
            if sink.currency == currency:
                expense_breakdown[key] = sink.expected_value
                total_expense += sink.expected_value
        
        # Calculate net flow
        net_flow = total_income - total_expense
        
        # Determine status
        if net_flow > total_income * 0.2:
            status = BalanceStatus.SURPLUS
        elif net_flow < -total_expense * 0.2:
            if net_flow < -total_expense * 0.5:
                status = BalanceStatus.CRITICAL
            else:
                status = BalanceStatus.DEFICIT
        else:
            status = BalanceStatus.BALANCED
        
        # Calculate sustainability
        config = self.currency_configs.get(currency, {"initial": 0, "critical": 0})
        initial = config["initial"]
        critical = config["critical"]
        
        if net_flow >= 0:
            sustainability = 999  # Infinite
        elif initial > critical:
            sustainability = int((initial - critical) / abs(net_flow))
        else:
            sustainability = 0
        
        # Generate recommendations
        recommendations = self._generate_balance_recommendations(
            currency, total_income, total_expense, net_flow, status
        )
        
        return BalanceReport(
            currency=currency,
            income_per_period=total_income,
            expense_per_period=total_expense,
            net_flow=net_flow,
            status=status,
            sustainability_periods=sustainability,
            recommendations=recommendations,
            income_breakdown=income_breakdown,
            expense_breakdown=expense_breakdown
        )
    
    def analyze_difficulty(self, period: str = "all") -> DifficultyReport:
        """Analyze the difficulty curve.
        
        Args:
            period: Which period to analyze ("early", "mid", "late", or "all")
            
        Returns:
            DifficultyReport with analysis
        """
        checks = list(self.stat_checks.values())
        
        if not checks:
            return DifficultyReport(
                period=period,
                average_threshold=0,
                pass_rate_estimate=1.0,
                hardest_checks=[],
                easiest_checks=[],
                recommendations=["No stat checks found in the story"]
            )
        
        # Calculate average threshold
        thresholds = [c.threshold for c in checks]
        avg_threshold = sum(thresholds) / len(thresholds)
        
        # Estimate pass rate with default stats (50)
        default_stat = 50
        passes = sum(1 for c in checks if default_stat >= c.threshold)
        pass_rate = passes / len(checks)
        
        # Find extremes
        sorted_checks = sorted(checks, key=lambda c: c.threshold, reverse=True)
        hardest = [(c.action_id, c.threshold) for c in sorted_checks[:3]]
        easiest = [(c.action_id, c.threshold) for c in sorted_checks[-3:]]
        
        # Generate recommendations
        recommendations = []
        if avg_threshold > 55:
            recommendations.append("Average difficulty is high. Consider lowering some thresholds.")
        elif avg_threshold < 35:
            recommendations.append("Average difficulty is low. Consider raising some thresholds for challenge.")
        
        if pass_rate < 0.5:
            recommendations.append("Pass rate is low. Players may feel frustrated.")
        elif pass_rate > 0.9:
            recommendations.append("Pass rate is very high. Consider adding harder challenges.")
        
        return DifficultyReport(
            period=period,
            average_threshold=avg_threshold,
            pass_rate_estimate=pass_rate,
            hardest_checks=hardest,
            easiest_checks=easiest,
            recommendations=recommendations
        )
    
    def suggest_reward(
        self,
        action_type: str,
        difficulty: DifficultyLevel,
        currency: str
    ) -> Tuple[int, int]:
        """Suggest an appropriate reward range based on balance.
        
        Args:
            action_type: Type of action (work, quest, trade, etc.)
            difficulty: Difficulty of the action
            currency: Which currency to reward
            
        Returns:
            (min_reward, max_reward) tuple
        """
        # Base rewards by action type
        base_rewards = {
            "work": (3, 8),
            "quest": (10, 25),
            "trade": (1, 5),
            "exploration": (2, 6),
            "combat": (5, 15),
            "social": (1, 3)
        }
        
        base_min, base_max = base_rewards.get(action_type, (2, 5))
        
        # Difficulty multiplier
        multipliers = {
            DifficultyLevel.TRIVIAL: 0.5,
            DifficultyLevel.EASY: 0.8,
            DifficultyLevel.NORMAL: 1.0,
            DifficultyLevel.HARD: 1.3,
            DifficultyLevel.VERY_HARD: 1.6
        }
        mult = multipliers.get(difficulty, 1.0)
        
        # Adjust for current balance
        balance = self.analyze_balance(currency)
        if balance.status == BalanceStatus.DEFICIT:
            mult *= 1.2  # Slightly increase rewards if economy is tight
        elif balance.status == BalanceStatus.SURPLUS:
            mult *= 0.9  # Slightly decrease if too easy
        
        return (int(base_min * mult), int(base_max * mult))
    
    def suggest_threshold(
        self,
        attribute: str,
        difficulty: DifficultyLevel,
        period: str = "mid"
    ) -> int:
        """Suggest a stat check threshold.
        
        Args:
            attribute: Which attribute to check
            difficulty: Desired difficulty
            period: Game period (early/mid/late)
            
        Returns:
            Suggested threshold value
        """
        settings = self.difficulty_settings.get(period, self.difficulty_settings["mid"])
        
        if difficulty == DifficultyLevel.TRIVIAL:
            return settings["easy"] - 10
        elif difficulty == DifficultyLevel.EASY:
            return settings["easy"]
        elif difficulty == DifficultyLevel.NORMAL:
            return settings["normal"]
        elif difficulty == DifficultyLevel.HARD:
            return settings["hard"]
        else:  # VERY_HARD
            return settings["hard"] + 10
    
    def extract_from_story(self, story: Dict[str, Any]):
        """Extract numerical design data from an existing story.
        
        Args:
            story: The story data to analyze
        """
        # Configure currencies from initial_variables
        initial_vars = story.get("initial_variables", {})
        for var_id, value in initial_vars.items():
            if isinstance(value, (int, float)):
                # Detect currency patterns
                if any(p in var_id.lower() for p in ["coin", "gold", "voucher", "credit", "point"]):
                    self.configure_currency(var_id, int(value))
                # Detect attribute patterns
                elif any(p in var_id.lower() for p in ["constitution", "intelligence", "agility", "strength"]):
                    self.configure_attribute(var_id, int(value))
        
        # Extract from nodes
        nodes = story.get("nodes", {})
        if isinstance(nodes, dict):
            for node_id, node_data in nodes.items():
                self._extract_from_node(node_id, node_data)
    
    def _extract_from_node(self, node_id: str, node_data: Dict[str, Any]):
        """Extract numerical data from a node."""
        actions = node_data.get("actions", [])
        
        for action in actions:
            if not isinstance(action, dict):
                continue
            
            action_id = action.get("id", "")
            effects = action.get("effects", [])
            conditions = action.get("conditions", [])
            
            # Extract income/expense from calculate effects
            for effect in effects:
                if not isinstance(effect, dict):
                    continue
                
                if effect.get("type") == "calculate":
                    target = effect.get("target", effect.get("variable", ""))
                    operation = effect.get("operation", "")
                    value = effect.get("value", effect.get("operand", 0))
                    
                    if isinstance(value, (int, float)):
                        if operation in ["add", "+"]:
                            self.add_income_source(IncomeSource(
                                action_id=action_id,
                                node_id=node_id,
                                currency=target,
                                min_value=int(value),
                                max_value=int(value)
                            ))
                        elif operation in ["subtract", "-"]:
                            self.add_expense_sink(ExpenseSink(
                                action_id=action_id,
                                node_id=node_id,
                                currency=target,
                                min_value=int(value),
                                max_value=int(value)
                            ))
            
            # Extract stat checks from conditions
            for condition in conditions:
                if not isinstance(condition, dict):
                    continue
                
                if condition.get("type") == "variable":
                    variable = condition.get("variable", "")
                    operator = condition.get("operator", "")
                    value = condition.get("value", 0)
                    
                    # Only track >= checks as difficulty checks
                    if operator in ["gte", ">=", "gt", ">"]:
                        difficulty = self._infer_difficulty(int(value))
                        self.add_stat_check(StatCheck(
                            action_id=action_id,
                            node_id=node_id,
                            attribute=variable,
                            threshold=int(value),
                            difficulty=difficulty
                        ))
    
    def _infer_difficulty(self, threshold: int) -> DifficultyLevel:
        """Infer difficulty level from a threshold."""
        if threshold <= 25:
            return DifficultyLevel.TRIVIAL
        elif threshold <= 35:
            return DifficultyLevel.EASY
        elif threshold <= 50:
            return DifficultyLevel.NORMAL
        elif threshold <= 65:
            return DifficultyLevel.HARD
        else:
            return DifficultyLevel.VERY_HARD
    
    def _generate_balance_recommendations(
        self,
        currency: str,
        income: float,
        expense: float,
        net_flow: float,
        status: BalanceStatus
    ) -> List[str]:
        """Generate recommendations based on balance analysis."""
        recommendations = []
        
        if status == BalanceStatus.CRITICAL:
            recommendations.append(
                f"CRITICAL: {currency} has severe deficit ({net_flow:.1f}/period). "
                f"Players will run out quickly. Consider adding more income sources."
            )
        elif status == BalanceStatus.DEFICIT:
            recommendations.append(
                f"WARNING: {currency} has deficit ({net_flow:.1f}/period). "
                f"This may create tension but could frustrate players."
            )
        elif status == BalanceStatus.SURPLUS:
            if net_flow > income * 0.5:
                recommendations.append(
                    f"NOTE: {currency} has large surplus ({net_flow:.1f}/period). "
                    f"Resources may feel too abundant. Consider adding meaningful expenses."
                )
        
        if income == 0:
            recommendations.append(
                f"No income sources found for {currency}. "
                f"Players cannot earn this resource."
            )
        
        if expense == 0 and income > 0:
            recommendations.append(
                f"No expenses found for {currency}. "
                f"Consider adding meaningful ways to spend this resource."
            )
        
        return recommendations
    
    def to_context_string(self) -> str:
        """Generate a context string for LLM prompts.
        
        Returns a summary of the numerical design for inclusion in prompts.
        """
        lines = ["# NUMERICAL DESIGN CONTEXT"]
        
        # Currency balances
        lines.append("\n## Economy Status")
        for currency_id in self.currency_configs.keys():
            report = self.analyze_balance(currency_id)
            lines.append(
                f"- {currency_id}: {report.status.value} "
                f"(income={report.income_per_period:.1f}, expense={report.expense_per_period:.1f}, "
                f"net={report.net_flow:.1f})"
            )
        
        # Difficulty overview
        diff_report = self.analyze_difficulty()
        lines.append("\n## Difficulty Overview")
        lines.append(f"- Average threshold: {diff_report.average_threshold:.1f}")
        lines.append(f"- Estimated pass rate: {diff_report.pass_rate_estimate:.1%}")
        
        # Recommendations
        all_recs = []
        for currency_id in self.currency_configs.keys():
            report = self.analyze_balance(currency_id)
            all_recs.extend(report.recommendations)
        all_recs.extend(diff_report.recommendations)
        
        if all_recs:
            lines.append("\n## Recommendations")
            for rec in all_recs[:5]:  # Limit to top 5
                lines.append(f"- {rec}")
        
        return "\n".join(lines)
