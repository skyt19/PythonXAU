# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Plain static HTML/CSS — no framework, no build step, served as static files.

## Users

Students and hobbyists tracking their own open-source and side projects. They open the dashboard to answer a narrow question quickly: *what is my work actually doing right now* — which repos are active, what is stuck, what shipped this week. They are not enterprise operators; they may have two repos or twenty, and they are often the only person who maintains them.

## Product Purpose

A personal project-tracking dashboard that reads a person's public GitHub activity and turns it into a legible picture of their work in progress. Success means the user can read their status in one screen without scrolling, and trust what they're reading.

## Positioning

The mechanism is **live public GitHub data as the single source of truth**, rendered as a working view of projects rather than a vanity activity graph. Neighboring products (contribution heatmaps, GitHub-style profile dashboards) show the *user's* contribution history to an audience; this shows the *user's own projects to the user*, organized around work-in-progress and blockers instead of commit volume. The differentiator is the project-centered framing: repos, not commit squares.

## Operating Context

- The tool runs entirely client-side in the browser; there is no server, no account, no persistence beyond what the browser holds.
- Data comes from the public GitHub REST API over unauthenticated requests, which are rate-limited (60 requests/hour per IP). The dashboard must be tolerant of rate-limit and network failure rather than assume success.
- The user identifies which GitHub account to read via configuration in the page. This is a deliberate, user-set input, not an inferred one.
- Viewing is realistic on a laptop first and a phone second; a student checking this between classes is a real scenario.

## Capabilities and Constraints

- **Dashboard view** (primary): the user's repositories with per-project status — recent activity, open issues, open pull requests, last push, primary language.
- **Detail view** (secondary): a single project expanded to its issues, pull requests, and recent commits.
- **Live public GitHub API only.** No authentication, no token, no private repositories, no write operations of any kind.
- **Static delivery.** No build step, no server-side rendering, no framework runtime.
- **Rate limiting is a first-class state.** The dashboard must degrade honestly — show that it was throttled or offline rather than showing empty or stale data as if it were real.
- **System typeface only for now.** No bundled or licensed brand fonts in the current scope.
- **Undecided:** which GitHub account the dashboard targets, and whether repository selection is manual, automatic (all public repos), or a mix. The UI must not assume either until answered.

## Brand Commitments

None established. The product is a working instrument, not a branded campaign; identity should read as precise and quiet rather than promotional. No name has been chosen for the product itself.

## Evidence on Hand

- The live GitHub REST API (public endpoints) is the data source and is available to fetch against.
- The user will supply real content and assets — logos, screenshots, project imagery — but none exist in the repository yet.
- **Absent, and must not be fabricated:** testimonials, customer names, usage statistics, benchmark claims, or any statement about how many people use this. There is no product to have users yet.

## Product Principles

1. **Read the state, don't perform it.** Every number on screen comes from the API or is absent. No fabricated activity, no decorative metrics.
2. **Honest degradation beats fake success.** Rate-limited, offline, and empty-repo states are designed states, not error leftovers.
3. **One screen, one answer.** The dashboard's job is the current picture of all projects at once; detail is one click away, never in the way.
4. **Real work over vanity metrics.** Frame projects by what is in flight, not by commit counts.
5. **The tool recedes.** Dense, scannable, fast; the interface should be readable in a glance and unobtrusive the rest of the time.

## Accessibility & Inclusion

WCAG 2.1 AA is the working standard. Beyond that, the dashboard must remain legible and fully usable at narrow widths and at 200% zoom, carry full keyboard operation for navigation and detail transitions, and convey state (status, error, loading) through more than color alone.
