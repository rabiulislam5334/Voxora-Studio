# TS-02 — Remotion v4.0.543 Licence Eligibility Audit

> Audit date: 2026-11-25  
> Audited upstream ref: `v4.0.543`  
> Scope: Remotion software licence only; not a complete third-party dependency, browser, codec or binary audit.  
> Decision: **PERSONAL EVALUATION ELIGIBLE FOR AN INDIVIDUAL; VOXORA DESKTOP REDISTRIBUTION NOT CLEARED.**

## 1. Exact version-pinned source

The audited file is the `LICENSE.md` at the immutable upstream tag:

- [remotion-dev/remotion — LICENSE.md at v4.0.543](https://github.com/remotion-dev/remotion/blob/v4.0.543/LICENSE.md)

The tag-pinned licence states:

- Individuals are eligible for the Free License.
- Free License users may use Remotion commercially or non-commercially for creating videos and images, and modify it for their own custom use case.
- It prohibits copying or modifying Remotion code for the purpose of selling, renting, licensing, relicensing or sublicensing a derivative of Remotion.
- Users outside the Free License eligibility group must obtain a Company License.

This is a source-available proprietary licence, not an OSI-approved open-source licence. Public source visibility does not make it an unrestricted redistribution licence.

## 2. Voxora-specific interpretation

| Voxora scenario | Evidence-based status | Reason |
|---|---|---|
| The owner uses Remotion personally to create their own videos | **ELIGIBLE UNDER THE INDIVIDUAL FREE-LICENSE CATEGORY** | The v4.0.543 licence expressly lists individuals and permits commercial or non-commercial video/image creation. |
| Voxora invokes a separately installed Remotion runtime for the owner's personal workflow | **POTENTIALLY ELIGIBLE; KEEP OPT-IN** | The owner remains the individual user, but the exact installation/integration arrangement should not be treated as a redistribution grant. |
| Voxora bundles Remotion packages/runtime into its distributed Windows installer | **NOT CLEARED** | The v4.0.543 licence does not expressly grant third-party desktop-app bundling or redistribution rights. Its derivative-sale restriction does not, by itself, answer every bundling scenario. |
| Voxora redistributes a modified Remotion runtime or a Remotion-derived product | **NOT CLEARED; HIGH LICENCE RISK** | The licence expressly restricts selling, renting, licensing, relicensing or sublicensing a derivative of Remotion. |
| Voxora later becomes a commercial product used by a team/company | **REQUIRES ELIGIBILITY REVIEW** | The free category is entity- and use-dependent; do not assume an individual developer's eligibility extends to every future company or deployment model. |

**Important boundary:** this audit does not conclude that desktop bundling is definitely prohibited. It concludes that the exact v4.0.543 licence text inspected does not expressly establish permission for Voxora to redistribute Remotion as part of its own desktop product. Do not infer permission from the individual free-use clause.

## 3. Current documentation is not a substitute for the pinned licence

Remotion's current licensing pages and Terms may describe newer licensing models and additional product-distribution scenarios. Those pages must not be silently substituted for the licence shipped at the pinned `v4.0.543` tag.

Before any framework selection, capture a written answer from Remotion covering the exact proposed distribution model:

1. Voxora is a Windows desktop application.
2. Voxora may bundle the Remotion runtime and its required packages, or alternatively require users to install Remotion separately.
3. Voxora automates video creation from a user's script and supplied narration.
4. The application may later be distributed commercially.
5. The intended deployment is local-first; Voxora does not provide a hosted rendering service.

Retain the written answer, applicable licence version, any required company/automation fees, telemetry obligations and redistribution conditions in the decision record.

## 4. Recommended TS-02 handling

- Keep Remotion as a benchmarked candidate, not the selected primary adapter.
- Do not bundle or redistribute Remotion in Voxora until written permission or an applicable licence clearly covers the exact desktop distribution model.
- If the user wants to continue personal evaluation, keep it isolated and user-installed/opt-in; do not make it a mandatory Voxora dependency.
- Keep the renderer-neutral adapter boundary so another candidate can be selected without changing the Universal Core.
- Preserve FFmpeg as Voxora's final encoding/mux backbone.
- This licence review does not clear Remotion's 407-entry lockfile, transitive dependency notices, browser/runtime binaries, or target-PC performance.

## 5. Evidence and remaining gates

| Gate | Result |
|---|---|
| Exact v4.0.543 licence text | **SOURCE VERIFIED** |
| Individual free-use category | **SOURCE VERIFIED** |
| Explicit third-party desktop-app redistribution permission in v4.0.543 licence | **NOT ESTABLISHED** |
| Written vendor clarification for Voxora distribution | **OPEN** |
| Exact dependency/lockfile licence and notice audit | **OPEN** |
| Browser/binary and offline runtime closure | **OPEN** |
| Target-PC render/performance acceptance | **OPEN** |

This is an engineering licence-risk assessment, not legal advice. No package was installed, no Remotion runtime was bundled, and no user project files were changed during this audit.
