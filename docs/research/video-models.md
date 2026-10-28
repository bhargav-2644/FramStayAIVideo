# Video model research (October 2026)

Which image-to-video model should turn 3 to 6 property photos into a slow,
drone-style teaser that keeps the real building's shape? This updates the
model table in the September blueprint, which is now out of date on both
rankings and prices.

All prices below come from third-party blogs, aggregators and resellers found
by web search on 2026-10-23; the official pricing pages could not be opened
from this environment. Treat every number as approximate and confirm it on the
provider's own page before spending money.

## What changed since the blueprint

- **Kling slipped.** Kling 3.0 Pro now sits around 18th to 19th on both public
  image-to-video leaderboards, behind Gemini Omni Flash, Seedance 2.5 and
  Wan 3.0.
- **Kling's price was understated.** The blueprint used $0.112 a second for
  Kling 3.0 Pro; current reseller figures for Pro image-to-video are about
  $0.22 to $0.24 a second without audio. At that rate a teaser with one retry
  per shot costs about Rs 590, over the Rs 350 per lead target.
- **New cheap tiers exist.** Veo 3.1 Lite and Fast, Gemini Omni Flash and
  hosted Wan 3.0 all come in around $0.05 to $0.12 a second, which makes the
  Rs 350 target easy.
- **Wan 3.0 is not open weights.** Despite blog claims, no official Wan 3.0
  weights or licence were found; it is API-only. Wan 2.2 (Apache 2.0) is still
  the newest confirmed self-hostable Wan.

## Leaderboards

| Board | Top of the list | Kling 3.0 Pro |
|---|---|---|
| [Artificial Analysis I2V, with audio](https://artificialanalysis.ai/video/leaderboard/image-to-video) | Seedance 2.5 3rd (Elo 1138), Gemini Omni Flash 1.1 4th (1132), Wan 3.0 5th (1127) | 18th (1004) |
| Artificial Analysis I2V, no audio | Gemini Omni Flash 1st (Elo 1366) | not found |
| [Arena I2V](https://arena.ai/leaderboard/video/image-to-video) (Sept 2026) | Gemini Omni 1.1 Flash 2nd (1488), Seedance 2.5 720p 4th (1477) | 19th (1354) |

Leaderboards rate general video appeal, mostly people and action. None
measures whether a real roofline, pool shape or window grid survives a camera
move, which is the thing that matters here. Only our own bake-off can answer
that.

## Candidates

Prices are per second of output, video without audio unless noted. Teaser cost
is a 15 second teaser (3 clips of 5 s), one pass; double it for one retry per
shot. Rupees at about Rs 88 to the dollar.

| Model | Price per second | 15 s teaser, one pass | Clip length | Notes |
|---|---|---|---|---|
| Gemini Omni Flash (Google, preview) | ~$0.10 at 720p ([eesel](https://www.eesel.ai/blog/gemini-omni-flash-pricing)); more at higher resolutions | ~$1.50 (Rs 130) | 3 to 10 s | Tops the silent I2V board; preview only, 720p in the API, no free tier; model ID `gemini-omni-flash-preview` |
| Veo 3.1 Lite | $0.05 at 720p, $0.08 at 1080p ([benchlm](https://benchlm.ai/media-pricing/veo)) | $0.75 to $1.20 (Rs 65 to 105) | up to 8 s | Cheapest serious option; good for drafts |
| Veo 3.1 Fast | $0.10 at 720p, $0.12 at 1080p, $0.30 at 4K ([benchlm](https://benchlm.ai/media-pricing/veo)) | ~$1.80 at 1080p (Rs 160) | up to 8 s | Supports first and last frame |
| Veo 3.1 | $0.40 at 720p/1080p, $0.60 at 4K ([benchlm](https://benchlm.ai/media-pricing/veo)) | ~$6 (Rs 530) | up to 8 s | Premium finals only |
| Seedance 2.5 (ByteDance) | official BytePlus ~$0.23 at 720p, ~$0.57 at 1080p; fal ~$1.16 at 1080p ([useapi](https://useapi.net/docs/articles/seedance-2-api-pricing), [ArgoLink](https://argolink.io/en/blog/seedance-2-5-api-pricing)) | ~$3.50 at 720p, ~$8.50 at 1080p | 4 to 30 s | Strongest identity preservation; up to 50 reference inputs, so several photos of one property can anchor one shot; also on Higgsfield |
| Wan 3.0 (Alibaba, hosted) | $0.05 at 480p, $0.10 at 720p, $0.20 at 1080p on fal ([Atlas Cloud](https://www.atlascloud.ai/blog/tips/is-wan-3.0-open-source)) | $1.50 at 720p, $3 at 1080p | n/a | 5th on AA board; commercial terms still unsettled, check before selling |
| Kling 3.0 Pro | ~$0.224 no audio (Segmind, fal); Krea lists $0.235 ([Krea](https://www.krea.ai/blog/kling-3-0-api-access-guide-pricing-code-examples-for-multi-shot-ai-video)) | ~$3.40 (Rs 300) | 3 to 15 s | Good physics, but now behind on rankings and over budget with retries |
| Kling 3.0 Turbo | $0.106 to $0.132 at 720p/1080p ([EvoLink](https://evolink.ai/kling-3-0-turbo)) | ~$1.60 to $2 | n/a | Cheaper Kling for drafts |
| Wan 2.2 A14B (open weights, Apache 2.0) | free to run; ~$0.06 to $0.10 per 5 s clip on a rented RTX 4090 | ~$0.30 | n/a | Only worth it at hundreds of clips a week |

Earlier blueprint figures for Kling 2.5 Turbo, Sora 2 Pro and Hailuo 2.3 were
not rechecked; none of them ranks near the top any more.

## Getting geometry right

No source benchmarks building fidelity in drone-style moves, and the research
papers on geometric consistency (for example
[VideoWeave](https://arxiv.org/pdf/2606.14162)) are not products. What the
sources and the blueprint agree on:

- **Keep moves short and slow.** A 5 s push-in or rise invents far less of the
  property than an orbit.
- **Anchor with more than one image.** Use first-and-last-frame (Veo 3.1) or
  multi-reference (Seedance 2.5) so the model sees the property from both ends
  of the move instead of guessing.
- **Start from wide or elevated photos.** A ground-level photo cannot become a
  true bird's-eye flight.
- **Possible experiment:** Higgsfield's 3D scene tools can generate new camera
  angles of one location and then drive Seedance 2.5 from them. That might hold
  the building's shape better than a single photo, but it is untested and paid.

## Recommendation

1. **Redo the bake-off shortlist** as Gemini Omni Flash, Veo 3.1 Fast (Lite for
   drafts), Seedance 2.5 at 720p and Wan 3.0 at 720p, with Kling 3.0 Pro kept
   as the baseline from the blueprint.
2. **Run it on the same 5 properties and the same shot prompts**, scoring each
   clip on building fidelity, landscape fidelity, camera smoothness and retries
   needed, then pick on quality per rupee.
3. **Budget:** 5 properties x 3 shots x 5 models x 2 attempts is 150 clips. At
   about $0.50 to $0.60 per 5 s clip on the cheap tiers and about $1.15 for
   Seedance at 720p and Kling 3.0 Pro, expect roughly $120 (Rs 10,500). Cut it
   to 3 properties to bring that near $70.
4. **Update the unit economics.** If a $0.10 a second model wins, the teaser
   costs about $3 with retries (Rs 265), or about Rs 315 per lead with tools and
   hosting, so the Rs 350 target holds. If Kling 3.0 Pro wins, either drop
   retries or raise the target to about Rs 640.

## Still to verify

- Official prices on Google's Gemini API page, BytePlus ModelArk and Kling's
  Open Platform; whether the quoted Veo figures include audio.
- Commercial-use terms for Gemini Omni Flash (preview) and Wan 3.0.
- Whether Gemini Omni Flash accepts a last frame or several reference images.
- What Higgsfield charges in credits for each of these models.

## Sources

- [Artificial Analysis image-to-video leaderboard](https://artificialanalysis.ai/video/leaderboard/image-to-video)
- [Arena image-to-video leaderboard](https://arena.ai/leaderboard/video/image-to-video)
- [OpenRouter: Best image-to-video models compared](https://openrouter.ai/blog/insights/image-to-video-models-compared/)
- [Higgsfield: 10 best AI video models in 2026](https://higgsfield.ai/blog/5-Best-AI-Video-Models-2026-Tested-Compared)
- [3D AI Studio: Veo 3.1 vs Kling 3.0 vs Seedance 2.0](https://www.3daistudio.com/blog/best-ai-video-generator-2026)
- [eesel: Gemini Omni Flash pricing](https://www.eesel.ai/blog/gemini-omni-flash-pricing)
- [benchlm: Veo pricing](https://benchlm.ai/media-pricing/veo)
- [useapi: Seedance 2.0 and 2.5 API pricing](https://useapi.net/docs/articles/seedance-2-api-pricing)
- [ArgoLink: Seedance 2.5 API pricing, October 2026](https://argolink.io/en/blog/seedance-2-5-api-pricing)
- [Atlas Cloud: Is Wan 3.0 open source?](https://www.atlascloud.ai/blog/tips/is-wan-3.0-open-source)
- [imaginetovideo: Wan 3.0 status](https://imaginetovideo.com/wan-3-0)
- [Krea: Kling 3.0 API pricing](https://www.krea.ai/blog/kling-3-0-api-access-guide-pricing-code-examples-for-multi-shot-ai-video)
- [EvoLink: Kling 3.0 Turbo](https://evolink.ai/kling-3-0-turbo)
- [fal: AI image-to-video generators](https://fal.ai/learn/tools/ai-image-to-video-generators)
- [invideo: geometric accuracy in AI real estate videos](https://invideo.io/faq/how-do-you-make-ai-generated-real-estate-videos/)
