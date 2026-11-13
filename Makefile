# GNU Make supplies CXX=g++ implicitly; on macOS that is Apple Clang.
ifeq ($(origin CXX), default)
  ifeq ($(shell uname -s),Darwin)
    CXX := $(firstword $(wildcard /opt/homebrew/bin/g++-* /usr/local/bin/g++-*))
  else
    CXX := g++
  endif
endif
PYTHON ?= python3
CXXFLAGS ?= -O3 -std=c++17 -fopenmp -Wall -Wextra -Wpedantic
CPPFLAGS ?= -Isrc

.PHONY: all test test-integration clean sanitize
all: raytrace test_core
raytrace: src/main.cpp src/core.hpp src/png.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) src/main.cpp -o $@
test_core: tests/test_core.cpp src/core.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) tests/test_core.cpp -o $@
test: all
	./test_core
	$(PYTHON) tests/run_correctness.py
test-integration: all
	$(PYTHON) tests/test_proposal.py
	$(PYTHON) tests/test_metrics.py
	$(PYTHON) tests/test_web.py
sanitize:
	$(CXX) $(CPPFLAGS) -O1 -g -std=c++17 -fopenmp -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_core.cpp -o test_core_san
	./test_core_san
	$(CXX) $(CPPFLAGS) -O1 -g -std=c++17 -fopenmp -fsanitize=address,undefined -fno-omit-frame-pointer src/main.cpp -o raytrace_san
	./raytrace_san --scene bunny --mode tile-dynamic --threads 4 --width 67 --height 39 --spp 4
clean:
	rm -f raytrace test_core raytrace_san test_core_san
