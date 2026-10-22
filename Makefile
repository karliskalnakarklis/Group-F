# One stack runs at a time; the gateway listens on port 8000. Tests and
# measurements run in a container (tests/runner.sh).
#   <stack> is baseline, a or b.  LEVEL is v1 (default) or v2.
#
#   make up-<stack>            reset all data and start the stack
#   make test-<stack>          acceptance tests, version 1
#   make test-<stack>-v2       acceptance tests in their version 2 form + change request tests
#   make conformance-<stack>   data-ownership rules, checked in the compose file
#   make bench-<stack>         latency and hops per use case     -> bench/results/
#   make blast-<stack>         stop each service, see what still works -> bench/results/
#   make impact                how far the change requests spread (git tags v1..v2)
#   make logs / make down

COMPOSE = docker compose -p pos
RUN = ./tests/runner.sh
LEVEL ?= v1
stackdir = $(if $(filter baseline,$(1)),baseline,variant-$(1))
wait = $(RUN) $(1) python tests/wait_for_stack.py 90

.PHONY: down logs impact test-image

up-%:
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) -f $(call stackdir,$*)/docker-compose.yml up -d --build --remove-orphans --wait

down:
	$(COMPOSE) down -v --remove-orphans

logs:
	$(COMPOSE) logs -f

test-%-v2:
	$(call wait,$*)
	POS_LEVEL=v2 $(RUN) $* pytest tests/acceptance tests/cr

test-%:
	$(call wait,$*)
	POS_LEVEL=v1 $(RUN) $* pytest tests/acceptance

conformance-%:
	$(COMPOSE) -f $(call stackdir,$*)/docker-compose.yml config --format json | $(RUN) $* python tests/conformance/ownership.py

bench-%:
	$(call wait,$*)
	POS_LEVEL=$(LEVEL) $(RUN) $* python bench/measure.py > bench/results/$*-$(LEVEL)-bench.json

blast-%:
	$(call wait,$*)
	POS_LEVEL=$(LEVEL) ./bench/blast_radius.sh $* > bench/results/$*-$(LEVEL)-blast.json

impact:
	./bench/change_impact.sh v1 v2 | tee bench/results/change-impact.md

# Rebuild the test image, for example after tests/requirements.txt changed.
test-image:
	docker build -t pos-tests tests
