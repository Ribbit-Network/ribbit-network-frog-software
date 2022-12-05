# Ribbit Frog Software
[![Chat](https://img.shields.io/discord/870113194289532969.svg?style=flat-square&colorB=758ED3)](https://discord.gg/vq8PkDb2TC)

Ribbit Network is a large network of open-source, low-cost, Greenhouse Gas (CO2 and hopefully other gasses in the future) Detection Sensors. These sensor units will be sold by the Ribbit Network and will upload their data to the cloud, creating the world's most complete Greenhouse Gas dataset.

This respository contains the software for the Frog Sensor.


## Current Software

The current Ribbit Network Frog software is being developed for the [Frog Sensor Version 4.](https://github.com/Ribbit-Network/ribbit-network-frog-hardware)

## Building the Software

Fetch the submodules:

```shell
$ git submodule update --jobs 32 --init --recursive
```

Run tests:

```shell
$ make test
```

Build the firmware:

```shell
$ make build
```

Flash the firmware to a device connected to `/dev/ttyACM*`:

```shell
$ make flash
```

## Need Help?
[If you are not sure where to start or just want to chat join our developer discord here.](https://discord.gg/vq8PkDb2TC). You can also [start a discussion](https://github.com/Ribbit-Network/ribbit-network-frog-sensor/discussions) right here in Github.

# View the Data!
The first prototype sensors are up and running! [Here is some real data from our sensor network!](https://dashboard.ribbitnetwork.org/) (Note this dashboard is still experimental and may be down occasionally).

[See more about the cloud database here.](https://github.com/Ribbit-Network/ribbit-network-dashboard)

## Questions?
[Check out the Frequently Asked Questions section.](https://github.com/Ribbit-Network/ribbit-network-faq) If you don't see your question, let us know either in a Github Discussion or via Discord.

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
