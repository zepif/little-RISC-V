# little-RISC-V

A RISC-V core, first in Python, then in Verilog & C--, then on FPGA.

# Getting started

### Prerequisites
* [riscv-gnu-toolchain](https://github.com/riscv-collab/riscv-gnu-toolchain)
* icarus-verilog

On OS X, you can use [Homebrew](https://brew.sh) to install the dependencies:
```sh
brew install icarus-verilog riscv-gnu-toolchain
```

On Ubuntu, executing the following command should suffice:
```sh
sudo apt-get install icarus-verilog riscv-gnu-toolchain
```

On Fedora/CentOS/RHEL OS, executing the following command should suffice:
```sh
sudo yum install icarus-verilog riscv-gnu-toolchain
```
On Arch Linux, executing the following command should suffice:

```sh
sudo pacman install icarus-verilog riscv-gnu-toolchain
```

### Installation
1. Clone this repo
```sh
git clone https://github.com/zepif/little-RISC-V
cd little-RISC-V
 ```
2. Clone and build `riscv-tests`
```sh
git clone https://github.com/riscv/riscv-tests
cd riscv-tests
git submodule update --init --recursive
autoconf
./configure
make
make install
cd ..
```
3. Create a virtual environment (optional)
```sh
python3 -m venv env
source env/bin/activate
```
4. Install Python packages
```sh
pip install -r requirements.txt
```

# TODO

* Add M instructions for fast multiply and divide
* Switch to 64-bit
* Add "RISK" ML accelerator ("K" Standard Extension)


# Notes on Memory system

8 million elements (20MB) = 23-bit address path

I want to support a load/store instruction into 32x32 matrix register (2432 bytes) like this:
* Would be R-Type with rs1 and rs2 (64-bit)
* rs1 contains the 23-bit base address, plus two masks in the upper bytes (0 is no mask)
* rs2 contains two 24-bit strides for x and y. Several of these bits aren't connected
* "rd" is the extension register to load into / store from

Use some hash function on the addresses to avoid "bank conflicts", can upper bound the fetch time.
