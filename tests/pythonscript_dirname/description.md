Description of problems:

1.  

Work item fails on /obj/sop_geo_process/topnet1/mplay1/dirname2:
```
Error 
mplay1_dirname2_18016 failed to run script: Traceback (most recent call last):
File "mplay1_dirname2_script", line 14, in <module>
IndexError: list index out of range
```

Steps to reproduce:

- open the hip file 
- right click on /obj/sop_geo_process/topnet1/mplay1
- select 'cook with preflight'

The issue is somewhat intermittent, so you may have to delete all the written output and cook again to reproduce this.

Houdini Version:
18.5.596

OS:
Ubuntu 18.04

2.  

Open GL ROP will not render with Intel Iris Graphics - Macbook Pro

3.  

Items that cook have repeated operations where parms are set.  setting a parm if it already matches wastes more time than checking the value and setting it conditionally.  eg, these are repeated operations that occur every frame and shouldn't occur.

22:17:59.393: Requesting sub item 7 for batch ropfetch4_2316
22:17:59.396: Successfully loaded sub item ropfetch4_2324
22:17:59.396: Setting batch sub index to 7
22:17:59.396: Setting channels for wedge attrib "obj_sop_geo_process_dust_hip"
22:17:59.397: Setting value for "obj_sop_geo_process_dust_hip" with type "Parameter Value"
22:17:59.397: Parm "/obj/sop_geo_process/dust/hip" not found
22:17:59.397: Setting channels for wedge attrib "obj_sop_geo_process_dust_shot"
22:17:59.397: Setting value for "obj_sop_geo_process_dust_shot" with type "Parameter Value"
22:17:59.397: Setting parm "/obj/sop_geo_process/dust/shot" at index "0" to value "shot0010"
22:17:59.397: Setting channels for wedge attrib "obj_sop_geo_process_dust_seq"
22:17:59.397: Setting value for "obj_sop_geo_process_dust_seq" with type "Parameter Value"
22:17:59.397: Setting parm "/obj/sop_geo_process/dust/seq" at index "0" to value "seq0010"
22:17:59.397: Setting channels for wedge attrib "obj_sop_geo_process_dust_index_key"
22:17:59.397: Setting value for "obj_sop_geo_process_dust_index_key" with type "Parameter Value"
22:17:59.397: Parm "/obj/sop_geo_process/dust/index_key" not found
22:17:59.397: Setting channels for wedge attrib "obj_sop_geo_process_dust_variant"
22:17:59.397: Setting value for "obj_sop_geo_process_dust_variant" with type "Parameter Value"
22:17:59.397: Setting parm "/obj/sop_geo_process/dust/variant" at index "0" to value "wedge0"
22:17:59.397: Setting channels for wedge attrib "obj_sop_geo_process_dust_element"
22:17:59.397: Setting value for "obj_sop_geo_process_dust_element" with type "Parameter Value"
22:17:59.397: Setting parm "/obj/sop_geo_process/dust/element" at index "0" to value "sphere-dust"
22:17:59.397: Setting channels for wedge attrib "obj_sop_geo_process_dust_index_key_expanded"
22:17:59.397: Setting value for "obj_sop_geo_process_dust_index_key_expanded" with type "Parameter Value"
22:17:59.397: Parm "/obj/sop_geo_process/dust/index_key_expanded" not found
22:17:59.397: Setting channels for wedge attrib "obj_sop_geo_process_dust_index_key_unexpanded"
22:17:59.397: Setting value for "obj_sop_geo_process_dust_index_key_unexpanded" with type "Parameter Value"
22:17:59.397: Parm "/obj/sop_geo_process/dust/index_key_unexpanded" not found
22:17:59.397: Setting channels for wedge attrib "obj_sop_geo_process_dust_version"
22:17:59.397: Setting value for "obj_sop_geo_process_dust_version" with type "Parameter Value"
22:17:59.397: Setting parm "/obj/sop_geo_process/dust/version" at index "0" to value "2"