# Ribbit Frog Software
[![Chat](https://img.shields.io/discord/870113194289532969.svg?style=flat-square&colorB=758ED3)](https://discord.gg/vq8PkDb2TC)

Ribbit Network is a large network of open-source, low-cost, Greenhouse Gas (CO2 and hopefully other gasses in the future) Detection Sensors. These sensor units will be sold by the Ribbit Network and will upload their data to the cloud, creating the world's most complete Greenhouse Gas dataset.

This respository contains the software for the Frog Sensor.


## Current Software

The current Ribbit Network Frog software is being developed for the [Frog Sensor Version 4.](https://github.com/Ribbit-Network/ribbit-network-frog-hardware)

## Gettting Started / Dependancies
To get started, you'll need to install a few dependancies first.

### ESP IDF

We currently build and test with ESP-IDF v4.4.1.

```shell
mkdir -p ~/esp
cd ~/esp
git clone --recursive https://github.com/espressif/esp-idf.git
cd esp-idf
git checkout v4.4.1
git submodule update --init --recursive
./install.sh all
```

## Building the Software

Fetch the submodules:

```shell
$ git submodule update --jobs 32 --init --recursive
```

Set up ESP-IDF:

```shell
$ source ~/esp/esp-idf/export.sh
```

Run tests:

```shell
$ make test
```

Build the firmware:

```shell
$ make build
```

## Flash the ESP32

Connect the esp32 board to your computer using the USBC connection port on the esp32 and a cable that will connect to your computer.

Press and hold the "boot" button then press the "reset" button and release both at the same time (shown below). This puts the esp32 into a flashing mode.

![image](https://github.com/Ribbit-Network/ribbit-network-frog-software/assets/2559382/046c0e77-cf4e-4546-bbd3-f41e9f136bc7)

The device should now appear on your machine as a serial port like "/dev/ttyACM0".

Now the command below can be run to flash the software to the device.

```shell
$ make DEVICE=/dev/ttyACM0 flash
```

## Need Help?
[If you are not sure where to start or just want to chat join our developer discord here.](https://discord.gg/vq8PkDb2TC). You can also [start a discussion](https://github.com/Ribbit-Network/ribbit-network-frog-sensor/discussions) right here in Github.

# View the Data!
The first prototype sensors are up and running! [Here is some real data from our sensor network!](https://dashboard.ribbitnetwork.org/) (Note this dashboard is still experimental and may be down occasionally).

[See more about the cloud database here.](https://github.com/Ribbit-Network/ribbit-network-dashboard)

## Questions?
[Check out the Frequently Asked Questions section.](https://github.com/Ribbit-Network/ribbit-network-faq) If you don't see your question, let us know either in a Github Discussion or via Discord.

## Get Involved
Are you interested in getting more involved or leading an effort in the Ribbit Network project? We are recruiting for additional members to join the Core Team. [See the Open Roles and descriptions here.](https://ribbitnetwork.notion.site/Core-Team-Role-Postings-105df298e0634f179f8f063c01708069).

## Contributing
See the [Issues](https://github.com/keenanjohnson/ghg-gas-cloud/issues) section of this project for the work that I've currently scoped out to be done. Reach out to me if you are interested in helping out! The [projects section](https://github.com/Ribbit-Network/ribbit-network-frog-sensor/projects) helps detail the major efforts going on right now.

We have a [contributing guide](https://github.com/Ribbit-Network/ribbit-network-frog-sensor/blob/main/CONTRIBUTING.md) that details the process for making a contribution.

[If you are not sure where to start or just want to chat join our developer discord here.](https://discord.gg/vq8PkDb2TC). You can also [start a discussion](https://github.com/Ribbit-Network/ribbit-network-frog-software/discussions) right here in Github.

## Background Information
[See the Wiki for background research.](https://github.com/Ribbit-Network/ribbit-network-frog-sensor/blob/main/wiki/Background-Research.md) This project is inspired by some awesome research by incedible scientists in academia.

## Ribbit Network
Ribbit Network is a non-profit (501c3) creating the world's largest Greenhouse Gas Emissions dataset that will empower anyone to join in the work on climate and provide informed data for climate action. We're an all volunteer team building everything we do in the open-source community.

If you would like to consider sponsoring Ribbit Nework you can do [via this link](https://givebutter.com/ribbitnetwork). The money is used to pay for software fees, purchase R&D hardware and generally support the mission of Ribbit Network.

## Ribbit Network Code of Conduct
By participating in this project, you agree to follow the <a href="https://ribbitnetwork.notion.site/Ribbit-Network-Code-of-Conduct-and-anti-harassment-policy-cc998ef83e7d4ae7abc95508ee6f2b0d">Ribbit Network Code of Conduct and Anti-Harassement Policy</a>.
Violations can be reported anonymously by filling out this <a href="https://docs.google.com/forms/d/e/1FAIpQLSemQSAER8az1lNGoWkL1udsv6O8oPc1WQ3dvQ0b9fJSSMeetQ/viewform"> form </a>. 
