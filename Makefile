CONTROL_PLANE_DIR := control-plane
MESSAGE ?= Is the cluster healthy?

.PHONY: help fmt test build run chat chat-json clean

help:
	$(MAKE) -C $(CONTROL_PLANE_DIR) help

fmt:
	$(MAKE) -C $(CONTROL_PLANE_DIR) fmt

test:
	$(MAKE) -C $(CONTROL_PLANE_DIR) test

build:
	$(MAKE) -C $(CONTROL_PLANE_DIR) build

run:
	$(MAKE) -C $(CONTROL_PLANE_DIR) run

chat:
	$(MAKE) -C $(CONTROL_PLANE_DIR) chat MESSAGE="$(MESSAGE)"

chat-json:
	$(MAKE) -C $(CONTROL_PLANE_DIR) chat-json MESSAGE="$(MESSAGE)"

clean:
	$(MAKE) -C $(CONTROL_PLANE_DIR) clean
