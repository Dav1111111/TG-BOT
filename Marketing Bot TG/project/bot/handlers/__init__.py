from bot.handlers import (
    start_handler,
    message_handler,
    business_plan_handler,
    value_proposition_handler,
    help_handler,
    admin_handlers,
    inline_handler,
    feedback_handler,
    payment_handler
)

__all__ = ['register_handlers']

def register_handlers(dp):
    """Register all handlers with the dispatcher"""
    # Register basic command handlers
    start_handler.register_handlers(dp)

    # Register help handler
    help_handler.register_handlers(dp)

    # Register business plan handlers
    business_plan_handler.register_handlers(dp)

    # Register value proposition handlers
    value_proposition_handler.register_handlers(dp)

    # Register feedback handler
    feedback_handler.register_handlers(dp)

    # Register admin handlers
    admin_handlers.register_handlers(dp)

    # Register inline mode handlers
    inline_handler.register_handlers(dp)

    # Register payment handler
    payment_handler.register_handlers(dp)

    # Register general message handler (should be last)
    message_handler.register_handlers(dp)
