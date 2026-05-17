"""Shared Qt stylesheet helpers used across all UI views."""


def btn_style(primary: bool = False, danger: bool = False,
              small: bool = False, tiny: bool = False) -> str:
    """Return a QPushButton stylesheet string for the given variant."""
    if tiny:
        pad = "2px 6px"
    elif small:
        pad = "3px 8px"
    else:
        pad = "6px 12px"

    if primary:
        return (
            f"QPushButton {{ background: #2a6496; color: white; border: none; "
            f"border-radius: 4px; padding: {pad}; font-weight: bold; }}"
            "QPushButton:hover { background: #3a74a6; }"
            "QPushButton:disabled { background: #333; color: #555; }"
        )
    if danger:
        return (
            f"QPushButton {{ background: #5a2020; color: #e08080; border: none; "
            f"border-radius: 4px; padding: {pad}; }}"
            "QPushButton:hover { background: #7a3030; }"
            "QPushButton:disabled { color: #555; }"
        )
    return (
        f"QPushButton {{ background: #242424; color: #bbb; border: 1px solid #333; "
        f"border-radius: 4px; padding: {pad}; }}"
        "QPushButton:hover { background: #2e2e2e; border-color: #555; }"
        "QPushButton:disabled {{ color: #444; }}"
    )


def tab_btn_style(active: bool = False) -> str:
    """Return a QPushButton stylesheet for tab-style navigation buttons."""
    if active:
        return (
            "QPushButton { background: #1e3a5f; color: #7ab8e0; "
            "border: 1px solid #2a5a8a; border-radius: 4px; "
            "padding: 4px 14px; font-weight: bold; }"
        )
    return (
        "QPushButton { background: #1a1a1a; color: #777; "
        "border: 1px solid #2a2a2a; border-radius: 4px; padding: 4px 14px; }"
        "QPushButton:hover { background: #222; color: #aaa; }"
    )
