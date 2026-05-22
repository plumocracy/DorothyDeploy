BIN_DIR := bin
CONTROL_PLANE_BIN := $(BIN_DIR)/control-plane
DOROTHY_CHAT_BIN := $(BIN_DIR)/dorothy-chat
MESSAGE ?= Is the cluster healthy?

.PHONY: help fmt test build run chat chat-json clean

help:
	@printf '%s\n' 'Targets:'
	@printf '  %-12s %s\n' 'fmt' 'Format Go source files'
	@printf '  %-12s %s\n' 'test' 'Run Go tests'
	@printf '  %-12s %s\n' 'build' 'Build control-plane and dorothy-chat binaries'
	@printf '  %-12s %s\n' 'run' 'Run the control-plane HTTP server'
	@printf '  %-12s %s\n' 'chat' 'Send MESSAGE to the in-cluster agent'
	@printf '  %-12s %s\n' 'chat-json' 'Send MESSAGE and print full JSON response'
	@printf '  %-12s %s\n' 'clean' 'Remove built binaries'

fmt:
	gofmt -w cmd internal

test:
	go test ./...

build:
	mkdir -p $(BIN_DIR)
	go build -o $(CONTROL_PLANE_BIN) ./cmd/control-plane
	go build -o $(DOROTHY_CHAT_BIN) ./cmd/dorothy-chat

run:
	go run ./cmd/control-plane

chat:
	go run ./cmd/dorothy-chat -- "$(MESSAGE)"

chat-json:
	go run ./cmd/dorothy-chat --json -- "$(MESSAGE)"

clean:
	rm -rf $(BIN_DIR)
