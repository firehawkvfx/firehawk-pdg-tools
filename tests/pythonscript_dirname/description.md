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