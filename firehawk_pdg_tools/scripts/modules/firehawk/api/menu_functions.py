

def reload_pdg():
    print('...Reload PDG modules')
    import pdg

    types = pdg.TypeRegistry.types()
    rt = types.registeredType( pdg.registeredType.Scheduler, "localscheduler" )
    rt.reload()
    rt = types.registeredType( pdg.registeredType.Scheduler, "firehawklocalscheduler" )
    rt.reload()

    import firehawk_submit as firehawk_submit
    reload( firehawk_submit )
    import firehawk_dynamic_versions as firehawk_dynamic_versions
    reload( firehawk_dynamic_versions )
    # import firehawk.plugins
    # reload(firehawk.plugins)
    # import firehawk.api
    # reload(firehawk.api)

    # import firehawk_plugin_loader
    # output_prep = firehawk_plugin_loader.module_package('output_prep')
    # reload(output_prep)

    # import firehawk_plugin_loader
    # import firehawk.plugins
    # import firehawk.api
    # plugin_modules, api_modules=firehawk_plugin_loader.load_plugins(reload_module=True) # load modules in the firehawk.api namespace
