# Variant B: capability-aligned

The services follow what the business does.

## Rules

1. Besides the `gateway`, there are at least three application services.
2. Each service stands for a business capability, derived from the use cases
   (for example selling, returns, purchasing, running a till, reporting). The
   group derives its own cut and justifies it.
3. Each service owns the data its capability needs, in its own model. It may
   keep its own copy of data that another service is responsible for (for
   example product prices at the checkout). For every such copy, the design
   says who is the source and how the copy is kept up to date.
4. Inside a service, the names follow the language of the business, not the
   legacy tables. The design documents the translation.
5. The `gateway` routes requests and composes answers. It owns no business
   data.
6. After the DDD lecture, you analyse this variant as bounded contexts in
   `docs/domain.md` and may refine it. Say what you changed.

## What you put in this folder

- `docker-compose.yml` that starts the variant with `make up-b`
- one folder per service with its code and its `Dockerfile`

Follow the conventions in [`AGENTS.md`](../AGENTS.md).

## Checked by

`make conformance-b`: the stack rules and the data-ownership rules.
