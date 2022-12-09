# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file Copyright.txt or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION 3.5)

file(MAKE_DIRECTORY
  "/Users/keenan/esp/esp-idf/components/bootloader/subproject"
  "/Users/keenan/Documents/GitHub/ribbit-network-frog-software/esp-idf/build/bootloader"
  "/Users/keenan/Documents/GitHub/ribbit-network-frog-software/esp-idf/build/bootloader-prefix"
  "/Users/keenan/Documents/GitHub/ribbit-network-frog-software/esp-idf/build/bootloader-prefix/tmp"
  "/Users/keenan/Documents/GitHub/ribbit-network-frog-software/esp-idf/build/bootloader-prefix/src/bootloader-stamp"
  "/Users/keenan/Documents/GitHub/ribbit-network-frog-software/esp-idf/build/bootloader-prefix/src"
  "/Users/keenan/Documents/GitHub/ribbit-network-frog-software/esp-idf/build/bootloader-prefix/src/bootloader-stamp"
)

set(configSubDirs )
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "/Users/keenan/Documents/GitHub/ribbit-network-frog-software/esp-idf/build/bootloader-prefix/src/bootloader-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "/Users/keenan/Documents/GitHub/ribbit-network-frog-software/esp-idf/build/bootloader-prefix/src/bootloader-stamp${cfgdir}") # cfgdir has leading slash
endif()
