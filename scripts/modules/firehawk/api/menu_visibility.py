
def reload_pdg_visibility(kwargs):
    import hou
    node = kwargs["node"]
    category = node.type().category().name()
    if category != 'Top':
        return False
    return True