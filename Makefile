# GNU Make supplies CXX=g++ implicitly; on macOS that is Apple Clang.
ifeq ($(origin CXX), default)
  ifeq ($(shell uname -s),Darwin)
    CXX := $(firstword $(wildcard /opt/homebrew/bin/g++-* /usr/local/bin/g++-*))
    ifeq ($(CXX),)
      CXX := clang++
    endif
  else
    CXX := g++
  endif
endif
PYTHON ?= python3
CXXFLAGS ?= -O3 -std=c++17 -Wall -Wextra -Wpedantic
CPPFLAGS ?= -Isrc
ifeq ($(shell uname -s),Darwin)
  ifneq ($(findstring clang,$(shell $(CXX) --version 2>/dev/null)),)
    OMP_PREFIX ?= $(firstword $(wildcard /opt/homebrew/opt/libomp /usr/local/opt/libomp))
    ifeq ($(OMP_PREFIX),)
     ifneq ($(MAKECMDGOALS),clean)
      $(error OpenMP missing: install libomp or set OMP_PREFIX to its installation directory)
     endif
    endif
    OMPFLAGS := -Xpreprocessor -fopenmp -I$(OMP_PREFIX)/include
    LDLIBS += -L$(OMP_PREFIX)/lib -Wl,-rpath,$(abspath $(OMP_PREFIX)/lib) -lomp
  else
    OMPFLAGS := -fopenmp
  endif
else
  OMPFLAGS := -fopenmp
endif

.PHONY: all test test-integration clean sanitize
all: raytrace test_core
raytrace: src/main.cpp src/core.hpp src/png.hpp scripts/build_info.py Makefile
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(OMPFLAGS) src/main.cpp -o $@ $(LDLIBS)
	$(PYTHON) scripts/build_info.py --compiler '$(CXX)' --flags '$(CPPFLAGS) $(CXXFLAGS) $(OMPFLAGS) $(LDLIBS)'
test_core: tests/test_core.cpp src/core.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(OMPFLAGS) tests/test_core.cpp -o $@ $(LDLIBS)
test: all
	./test_core
	$(PYTHON) tests/run_correctness.py --output results/current/correctness.json
test-integration: all
	$(PYTHON) tests/test_proposal.py
	$(PYTHON) tests/test_metrics.py
	$(PYTHON) tests/test_web.py
	$(PYTHON) tests/test_benchmarks.py
sanitize:
	$(CXX) $(CPPFLAGS) $(OMPFLAGS) -O1 -g -std=c++17 -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_core.cpp -o test_core_san $(LDLIBS)
	./test_core_san
	$(CXX) $(CPPFLAGS) $(OMPFLAGS) -O1 -g -std=c++17 -fsanitize=address,undefined -fno-omit-frame-pointer src/main.cpp -o raytrace_san $(LDLIBS)
	./raytrace_san --scene bunny --mode tile-dynamic --threads 4 --width 67 --height 39 --spp 4
clean:
	rm -f raytrace test_core raytrace_san test_core_san
