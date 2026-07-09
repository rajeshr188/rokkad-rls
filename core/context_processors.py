from core.navigation import (
    get_navigation_items,
    get_navigation_sections,
    get_workspace_switcher_items,
    get_workspace_switcher_state,
)


def navigation(request):
    return {
        "nav_items": get_navigation_items(request),
        "nav_sections": get_navigation_sections(request),
        "workspace_switcher_items": get_workspace_switcher_items(request),
        "workspace_switcher_state": get_workspace_switcher_state(request),
    }
