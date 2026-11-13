CXX ?= g++
CXXFLAGS ?= -O3 -std=c++17 -fopenmp -Wall -Wextra -Wpedantic
CPPFLAGS ?= -Isrc

.PHONY: all test clean sanitize
all: raytrace test_core
raytrace: src/main.cpp src/core.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) src/main.cpp -o $@
test_core: tests/test_core.cpp src/core.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) tests/test_core.cpp -o $@
test: all
	./test_core
	python3 tests/run_correctness.py
sanitize:
	$(CXX) $(CPPFLAGS) -O1 -g -std=c++17 -fopenmp -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_core.cpp -o test_core_san
	./test_core_san
	$(CXX) $(CPPFLAGS) -O1 -g -std=c++17 -fopenmp -fsanitize=address,undefined -fno-omit-frame-pointer src/main.cpp -o raytrace_san
	./raytrace_san --scene many --mode tile-dynamic --threads 4 --width 67 --height 39 --spp 4
clean:
	rm -f raytrace test_core raytrace_san test_core_san
