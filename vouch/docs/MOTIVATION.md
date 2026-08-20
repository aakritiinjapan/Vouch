# Why this problem

Short version: self-healing scrapers solve the failure you can see, and create a quieter one you
can't. Vouch exists for the quiet one.

## The failure everyone plans for

A competitor redesigns their listing page. Your selectors stop matching. The scrape returns empty
rows, or throws. This failure is **loud** — it shows up as nulls, as a row count of zero, as an
exception in a log. Every scraping stack has some answer for it, and Bright Data Scraper Studio has
a good one: it rewrites the extraction automatically so the data keeps flowing.

## The failure nobody plans for

A heal can succeed and still be wrong.

The rewritten extraction runs clean. It returns the right number of rows, in the right shape, with
the right types, and every downstream validation passes. But it has started reading a *different
element* — the crossed-out original price instead of the sale price, or the shipping cost instead of
the item price.

Nothing reports an error, because by every structural measure nothing is wrong. The data is
well-formed. It just doesn't mean what the field name says it means.

This is worse than a broken scraper, because a broken scraper stops you. A silently mis-healed one
keeps feeding you numbers, and every system downstream treats them as fact.

## Why this costs real money

The 96-row run in [`sample_output.json`](sample_output.json) came off Newegg's GPU category page.
Two of the rows look like this:

| Product | Price | Shipping |
|---|---|---|
| ZOTAC ARCTICSTORM AIO GeForce RTX 5090 32GB | **$6,900.00** | **$19.99** |
| MSI Gaming GeForce RTX 5090 32GB | **$4,699.99** | **$19.99** |

A heal that grabs the shipping element instead of the price element reports that a $6,900 graphics
card now sells for $19.99. A repricer acting on that number doesn't fail loudly — it *works*
perfectly, and prices you against a competitor who does not exist. That's a 345× error delivered as
clean, well-formed, validated data.

A floor rule limits the damage, but it doesn't prevent it: you still cut to your floor and give up
real margin on every unit sold, on the strength of a number that was never real. And a floor rule
helps in one direction only. The mirror failure — reading the crossed-out original instead of the
sale price — pushes your price *above* the market and costs you the sale instead of the margin. No
floor protects you there.

The only thing that prevents either is checking whether the number means what it claims to.

## Why a repricer, and not a price tracker

The validation layer is the product. The repricer is the setting that makes it matter, and the
choice is deliberate.

Looking at a price is passive. If a tracker shows you a wrong number, you notice, you shrug, you
refresh. Reliability is nice-to-have — it reads as backend plumbing.

**Committing a price change against real money is not passive.** The moment a system is about to act
on a number, "is this number trustworthy?" stops being plumbing and becomes the thing the user
actually cares about. That's why the guardian lives inside a repricer: it's the context where a
held decision is obviously worth more than a fast one.

So the self-heal never surfaces to the seller as a healing animation. It surfaces as *"this price
change is held, because we couldn't confirm the source behind it"* — a decision that just protected
their margin.

## What we build, and what we don't

We do **not** build self-healing. Bright Data provides it, and it works.

We build the layer that decides whether a given heal is trustworthy enough to commit — and, when it
isn't, feeds its own diagnosis back as a sharper instruction so the next attempt is better aimed.

## In one sentence

> Scraper Studio keeps the data flowing when a site changes; Vouch makes sure it didn't quietly
> start lying — inside a product where trusting the number is the whole job.
