# motherduck-domain-01 — Context

Ubiquitous language for this domain: business terms, entities, source-system quirks, and
naming conventions the agents rely on when building, fixing, or advising on this domain's
data products.

## Language

<!--
Append one entry per term, as it surfaces (never pre-populate speculative terms):

**<Term>**:
One or two sentences — what it means in this domain, and why it matters to a data product.
_Avoid_: near-synonyms this domain has rejected, and why.
-->

**sale_total**:
The value of a sale — `quantity × unit_price`. It is **computed, not read**: no column in the sales source holds a sale total under any name, so every "high-value sale" rule compares against a derived figure rather than a landed one. It matters because that derivation must live in one place; a second consumer re-inventing it is how two reports end up disagreeing about which sales were large.
_Avoid_: calling it a source column, or treating `unit_price` alone as a sale's value — a $60 unit price is not a $60 sale.
