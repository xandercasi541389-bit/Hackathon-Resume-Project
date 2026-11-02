CXX ?= c++
CXXFLAGS = -std=c++17 -Wall -Wextra -O2 -I..

BUILD := build
APP := resume_parser
APP_SRCS := main.cpp parser.cpp text_extract.cpp json_writer.cpp
APP_OBJS := $(APP_SRCS:%.cpp=$(BUILD)/%.o)

TEST_SRCS := $(wildcard tests/*.cpp)
TEST_BINS := $(TEST_SRCS:tests/%.cpp=$(BUILD)/%)
# parser.cpp is only linked into tests when a parser test exists.
TEST_COMMON := text_extract.cpp json_writer.cpp
ifneq ($(wildcard tests/test_parser.cpp),)
TEST_COMMON += parser.cpp
endif

.PHONY: all test clean

all: $(APP)

$(APP): $(APP_OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^

$(BUILD)/%.o: %.cpp | $(BUILD)
	$(CXX) $(CXXFLAGS) -c -o $@ $<

$(BUILD):
	mkdir -p $(BUILD)

# Each test binary is built from its own source plus the shared modules.
$(BUILD)/%: tests/%.cpp $(TEST_COMMON) $(wildcard *.h) | $(BUILD)
	$(CXX) $(CXXFLAGS) -I. -o $@ $< $(TEST_COMMON)

test: $(TEST_BINS)
	@set -e; for t in $(TEST_BINS); do echo "== $$t"; ./$$t; done

clean:
	rm -rf $(BUILD) $(APP)
