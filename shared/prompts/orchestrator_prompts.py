"""
Orchestrator Agent Prompts

Implements: ReAct (Reasoning and Acting) + Few-Shot Learning
Purpose: Prevent infinite loops by showing correct dispatch patterns
"""

# Few-Shot Examples for ReAct pattern
# Shows Reasoning → Action chains to prevent incorrect dispatch sequences
FEW_SHOT_EXAMPLES = [
    # Example 1: After executor → must observe
    (
        "human",
        """SENDER: executor
TASK GOAL: Login to the app
CURRENT SCREEN ANALYSIS: N/A (screen has changed after click)
RECENT ACTION HISTORY:
  step=3 [executor] decision: Clicked 'Login' button"""
    ),
    (
        "assistant",
        """REASONING: The executor just performed a click action. The screen state has definitely changed. According to MANDATORY DISPATCH RULE 1, after executor I MUST dispatch OBSERVE to re-read the new screen state before any decision can be made. I cannot dispatch DECIDE or EXECUTE without knowing the current UI state.
ACTION: OBSERVE
INSTRUCTION: Read the new screen state after the login button was clicked
is_completed: False"""
    ),
    # Example 2: After observer → should decide
    (
        "human",
        """SENDER: observer
TASK GOAL: Complete purchase checkout
CURRENT SCREEN ANALYSIS:
SEMANTIC_MAP:
[1]: Header Text - Checkout
[2]: Input Field - Card Number
[3]: Input Field - Expiry Date
[4]: Primary Button - Pay Now
SUMMARY: The screen displays a checkout form with payment fields and a primary action button.
RECENT ACTION HISTORY:
  step=5 [observer] observer_analysis: Screen analyzed"""
    ),
    (
        "assistant",
        """REASONING: The observer has provided a complete semantic map of the current screen. The UI elements are known - I can see the checkout form with payment fields. According to the dispatch flow, after OBSERVE the next logical step is DECIDE to determine what action to take on this screen. The screen shows we're on the checkout page, so the next step should be entering payment information.
ACTION: DECIDE
INSTRUCTION: Enter test card details into the payment form and proceed with checkout
is_completed: False"""
    ),
    # Example 3: After failed reflector → must observe (recovery)
    (
        "human",
        """SENDER: reflector
TASK GOAL: Navigate to settings
CURRENT SCREEN ANALYSIS: Previous action failed
RECENT ACTION HISTORY:
  step=7 [reflector] evaluation: FAILED - Element not found on screen
  step=7 [executor] decision: Clicked 'Settings' button (but button not found)
REFLECTOR FEEDBACK — VERIFICATION FAILED:
The target element 'Settings' button was not found on current screen. The click may have targeted wrong coordinates."""
    ),
    (
        "assistant",
        """REASONING: The previous action failed because the target element was not found. According to MANDATORY DISPATCH RULE 6, after a failed reflector I MUST dispatch OBSERVE to re-evaluate the current screen state and recover. The screen state may have changed or we may be on a different screen entirely. I need fresh observer data before attempting any correction.
ACTION: OBSERVE
INSTRUCTION: Re-read the current screen to identify what UI elements are actually present
is_completed: False"""
    ),
    # Example 4: After successful reflector → complete or continue
    (
        "human",
        """SENDER: reflector
TASK GOAL: Add item to cart
CURRENT SCREEN ANALYSIS:
SEMANTIC_MAP:
[1]: Text - Item added to cart
[2]: Button - Continue Shopping
[3]: Button - Go to Cart
SUMMARY: Confirmation screen showing item was successfully added to cart.
RECENT ACTION HISTORY:
  step=4 [reflector] evaluation: PASSED - Action achieved expected result
  step=4 [executor] decision: Clicked 'Add to Cart' button
REFLECTOR FEEDBACK — VERIFICATION PASSED:
The action successfully added the item to cart. Confirmation message visible."""
    ),
    (
        "assistant",
        """REASONING: The reflector has confirmed the action was successful - the item was added to cart as shown by the confirmation message. The task goal was to 'Add item to cart' and this has been achieved. Since the ultimate expected result is met, I should dispatch COMPLETE to finalize the workflow.
ACTION: COMPLETE
INSTRUCTION: Task completed successfully - item added to cart with confirmation
is_completed: True"""
    ),
]
