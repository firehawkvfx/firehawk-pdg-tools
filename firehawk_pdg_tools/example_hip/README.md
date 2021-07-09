

An asset function will normally require JOB/SEQ/SHOT env vars to work.
From this directory, to open an example file....

In BASH:
```
export HOUDINI_PACKAGE_DIR=$PWD ; export JOB=myshow ; export SEQ=seq001 ; export SHOT=shot0010 ; houdini ./firehawk_pdg_tools/example_hip/firehawk.pdg.versioning_demo.hip
```

In TCSH:
```
setenv HOUDINI_PACKAGE_DIR $PWD ; setenv JOB myshow ; setenv SEQ seq001 ; setenv SHOT shot0010 ; houdini ./firehawk_pdg_tools/example_hip/firehawk.pdg.versioning_demo.hip
```