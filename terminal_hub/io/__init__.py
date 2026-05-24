"""User-facing IO: display strings, error messages, slugification.

Import the helpers from their modules directly so the submodule names stay
addressable (a package-level re-export named ``display`` would shadow the
``display`` submodule):

    from terminal_hub.io.display import display, load_data
    from terminal_hub.io.errors import msg
    from terminal_hub.io.slugify import slugify

JSON resources (`predefined_text.json`, `error_msg.json`) live next to the
loader that reads them.
"""
