#! /bin/bash

sudo apt-get update
sudo apt-get upgrade
sudo apt-get install emacs python-dev python-setuptools

# pyOsc
wget https://trac.v2.nl/raw-attachment/wiki/pyOSC/pyOSC-0.3.5b-5294.tar.gz
tar -xzvf pyOSC-0.3.5b-5294.tar.gz
cd pyOSC-0.3.5b-5294
sudo python setup.py install
cd ../
rm -rf pyOSC-0.3.5b-5294.tar.gz

# pySerial
wget https://pypi.python.org/packages/source/p/pyserial/pyserial-2.6.tar.gz
tar -xzvf pyserial-2.6.tar.gz
cd pyserial-2.6
sudo python setup.py install
cd ../
rm -rf pyserial-2.6.tar.gz

# pyHumod
wget http://pyhumod.googlecode.com/files/pyhumod-0.03.tar.gz
tar -xzvf pyhumod-0.03.tar.gz
cd pyhumod-0.03
sudo python setup.py install
cd ../
rm -rf pyhumod-0.03.tar.gz

# twython
git clone git://github.com/ryanmcgrath/twython.git
cd twython
sudo python setup.py install
cd ../

# peewee
git clone https://github.com/coleifer/peewee.git
cd peewee
sudo python setup.py install
cd ../

# wiringpi-python
git clone https://github.com/WiringPi/WiringPi-Python.git
cd WiringPi-Python
git submodule update --init
sudo python setup.py install
cd ../
