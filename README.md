## About

The `flipdisc` package provides utilities and a framework for writing flipdisc user apps using Python. The core component is required in order to build the bindings for the particle library, download one of those:

* [flipdisc-core for MacOS](https://s3.amazonaws.com/flipdisc-release/flipdisc-core/flipdisc-core-0.1-Darwin.tar.gz)
* [flipdisc-core for Linux](https://s3.amazonaws.com/flipdisc-release/flipdisc-core/flipdisc-core-0.1-Linux.tar.gz)


### Linux Requirements

```
sudo apt-get install python-dev python-virtualenv libffi-dev
```

It's common to set up a virtual environment for Python:

```
virtualenv ~/pyenv
source ~/pyenv/bin/activate
```


## Install

Install the flipdisc python package:

```
pip install numpy flipdisc
```
