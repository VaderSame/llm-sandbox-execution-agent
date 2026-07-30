"""Module containing the generate_report function."""

def generate_report() -> tuple[int, float]:
    """
    Compute the sum and average of a hardcoded list of integers.
    
    This function processes a predefined list of integers to calculate
    the total sum and average value. The list is hardcoded for demonstration
    purposes.
    
    Returns:
        tuple[int, float]: A tuple containing the total sum and the average value
        as a floating-point number.
    """
    numbers = [10, 20, 30]
    if not numbers:
        raise ValueError("List must contain at least one number")
    total_sum = sum(numbers)
    average = total_sum / len(numbers)
    return (total_sum, average)