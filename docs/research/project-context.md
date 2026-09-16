# SafeFlow AI research context

## Project identity

- **Title:** SafeFlow AI: A Formal Framework for Automata-Based AI Runtime Control
- **Researchers:** นายธีรเมธ สายคำ (673380273-9) and นายปวริศช์ ประมวล (673380278-9)
- **Advisor:** รศ. ดร.ชานนท์ เดชสุภา, College of Computing, Khon Kaen University
- **Academic context:** SC312701 Computer Science Seminar, preparation for the fourth-year senior project

## Architectural paradigm

SafeFlow studies a parallel, decoupled runtime-enforcement architecture. The AI agent may be trained independently, while an automata-based enforcer retains authority over proposed actions at deployment time. A violating proposal is intended to be blocked before it reaches the environment, with a separately defined safe fallback used in its place.

This differs from attempting to reverse engineer a modern neural network into an automaton. The safety model and the AI decision model remain separate.

The advisor's analogy is that an AI may learn abroad from arbitrary data, but when operating in Thailand it remains subject to Thai law. In the architecture, the automata policy represents that governing authority.

## Formal-methods basis

The desired safety relationship is:

```text
G_AI ⊆ G_Safe
```

The observed execution behavior must remain within the permitted safety graph. Runtime interception is positioned immediately before `env.step()` so a proposed action can be checked before it affects the simulated environment.

UPPAAL is intended for offline, design-time verification of the timed-automata safety model, including the absence of deadlock (`A[] not deadlock`). A verified transition table may later be represented as a constant-time Python lookup for runtime enforcement. This repository does not yet contain that implementation.

## Current simulation domain

- Simulator: Sinergym with EnergyPlus
- Environment: `Eplus-5zone-hot-discrete-v1`
- Action space: `Discrete(10)`, action identifiers 0 through 9
- AI agent: Stable-Baselines3 PPO using `MlpPolicy`
- Container image: `sinergym:latest`

The research focus is runtime control of externally supplied AI decisions, not development of a new reinforcement-learning algorithm.

## Current evidence boundary

The repository currently preserves only an unshielded, 10-step baseline trace. It demonstrates the form of data available for later runtime-policy evaluation; it does not constitute an implemented or formally verified safety enforcer.
