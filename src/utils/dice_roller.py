import random
import re

def get_expected_value(dice_str: str) -> float:
    """
    Calculates the expected (average) value of a dice roll string.
    e.g., "1d6" -> 3.5
    e.g., "2d8+2" -> 11.0
    e.g., "20~30" -> 25.0
    e.g., "5" -> 5.0
    """
    dice_str = dice_str.strip()

    # Handle simple number
    if dice_str.isdigit():
        return float(dice_str)

    # Handle range like "25~55"
    match = re.match(r'(\d+)\s*~\s*(\d+)', dice_str)
    if match:
        min_val, max_val = map(int, match.groups())
        return (min_val + max_val) / 2.0

    # Handle dice notation like "2d6+2"
    match = re.match(r'(\d+)d(\d+)([+-]\d+)?', dice_str, re.IGNORECASE)
    if match:
        num_dice, num_sides, modifier = match.groups()
        num_dice = int(num_dice)
        num_sides = int(num_sides)
        modifier = int(modifier) if modifier else 0

        if num_dice <= 0 or num_sides <= 0:
            return 0.0

        expected_dice_roll = num_dice * ((1 + num_sides) / 2.0)
        return expected_dice_roll + modifier
    
    return 0.0

def roll_dice(dice_str: str) -> int:
    """
    Rolls dice based on a string like '2d6', '1d20+5', or a range like '20~30'.
    """
    dice_str = dice_str.strip()

    # Handle simple number
    if dice_str.isdigit():
        return int(dice_str)

    # Handle range like "25~55"
    match = re.match(r'(\d+)\s*~\s*(\d+)', dice_str)
    if match:
        min_val, max_val = map(int, match.groups())
        return random.randint(min_val, max_val)

    # Handle dice notation like "2d6+2"
    match = re.match(r'(\d+)d(\d+)([+-]\d+)?', dice_str, re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid dice string: {dice_str}")
    
    num_dice, num_sides, modifier = match.groups()
    num_dice = int(num_dice)
    num_sides = int(num_sides)
    modifier = int(modifier) if modifier else 0
    
    if num_dice <= 0 or num_sides <= 0:
        raise ValueError("Number of dice and sides must be positive.")

    roll_total = sum(random.randint(1, num_sides) for _ in range(num_dice))
    return roll_total + modifier
