# DDD analysis

> Fill this in after the lecture on Domain-Driven Design. It analyses **both**
> variants as they are; it is not a third design. Delete the quoted guidance
> when you are done.

## Subdomains

> The subdomains of Frischwerk's business, each classified as core,
> supporting or generic, with a reason. Which one would Frischwerk build
> itself, which one buy?

| Subdomain | Type (core / supporting / generic) | Why |
|-----------|------------------------------------|-----|
| | | |

## Ubiquitous language

> The important terms, what they mean, and where the legacy names differ.
> Does a term mean the same in every service of variant B?

| Term | Meaning | Legacy name | Used in (variant B) |
|------|---------|-------------|---------------------|
| Sale | | ticket_system | |

## Aggregates and invariants

> Which rules must always hold, and which aggregate protects each of them?
> For example: a gift card balance never goes below zero.

| Aggregate | Invariant | Where it is enforced in A | Where it is enforced in B |
|-----------|-----------|----------------------------|----------------------------|
| | | | |

## Context map: variant A

> Every service as a context, with the relationship types between them
> (customer/supplier, conformist, anti-corruption layer, shared kernel,
> open host service, published language, partnership).

```mermaid
flowchart LR
```

## Context map: variant B

```mermaid
flowchart LR
```

## What the analysis changed

> Did you refine variant B after this analysis? What and why? What does the
> analysis say about variant A?
