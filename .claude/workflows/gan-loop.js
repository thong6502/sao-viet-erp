// .claude/workflows/gan-loop.js
// -----------------------------------------------------------------------------
// GAN LOOP ORCHESTRATOR (template). Drives steps 3-5 of the 3-role GAN loop:
//   3. generate (Builder)        -> .claude/skills/generate/SKILL.md
//   4. browser-validate (Eval.)  -> .claude/skills/browser-validate/SKILL.md
//   5. feedback rebuild          -> weakest criterion fed back to the Builder
//
// PRECONDITION: feature_list.json is ALREADY filled by the human-in-the-loop
// `plan` skill (step 2). This script does NOT plan; it only builds + scores +
// rebuilds one feature at a time. The `plan` skill stops to ask a human before
// it ever runs, so it is intentionally outside this automated orchestration.
//
// SCORING CONTRACT + thresholds: docs/EVALUATION.md
//   (4 criteria: design quality, originality, craft, functionality)
// LOOP / ROLE WIRING + budgets:  docs/ORCHESTRATION.md
//
// Wired for THIS project (React + Vite frontend + FastAPI backend). The APP run
// commands, the criteria, and the pass threshold below match docs/EVALUATION.md and
// the project's dev scripts (dev.ps1 / dev.sh). Tune the numbers if the rubric changes.
// -----------------------------------------------------------------------------

// `meta` MUST be a pure object literal (no function calls / variables) so the
// runner can statically read it without executing the body.
export const meta = {
  name: 'gan-loop',
  description:
    'For each planned feature: generate (build), browser-validate (score 4 ' +
    'criteria per docs/EVALUATION.md), and feed the weakest criterion back to ' +
    'the builder in a bounded rebuild loop until it passes or the budget is hit.',
  phases: ['build', 'validate', 'feedback-rebuild'],
};

// ---------------------------------------------------------------------------
// Tunable budget (see docs/ORCHESTRATION.md). Keep the loop BOUNDED so a
// feature that can never reach threshold cannot spin forever.
// ---------------------------------------------------------------------------
const MAX_ROUNDS = 3;          // generate -> validate attempts per feature
const PASS_THRESHOLD = 4;      // min score (1-5) on EACH criterion to pass (docs/EVALUATION.md)
const FEATURE_LIST = 'feature_list.json';

// The 4 evaluation criteria scored by the browser-validate Evaluator.
// Order/meaning is defined by docs/EVALUATION.md; this list is only used to
// describe the feedback contract to the agents.
const CRITERIA = ['design quality', 'originality', 'craft', 'functionality'];

// Real run commands for this project (mirror dev.ps1 / dev.sh). The Evaluator launches
// these, then drives APP.url with Playwright. Tip: ./dev.ps1 (Windows) or ./dev.sh (Unix)
// starts BOTH with one command.
const APP = {
  // Frontend dev server (React + Vite), from the repo root:
  frontend: 'cd frontend && npm run dev',
  // Backend API (FastAPI), from the repo root:
  backend: 'cd backend && python -m uvicorn app.main:app --port 8000 --reload',
  // URL the Evaluator navigates to with Playwright:
  url: 'http://localhost:5173',
};

export default function gan(ctx) {
  // ctx.features() reads the ALREADY-PLANNED feature_list.json (feat-001..N).
  // Build in dependency order; only act on features not yet passing.
  const features = ctx
    .features(FEATURE_LIST)
    .filter((f) => f.status !== 'passed');

  // pipeline(): features are processed sequentially (later features may depend
  // on earlier ones per feature_list.json `dependencies`). Use parallel() ONLY
  // if your features are provably independent.
  return pipeline(
    features.map((feature) =>
      phase(`feature:${feature.id}`, () => buildAndScore(ctx, feature)),
    ),
  );
}

// ---------------------------------------------------------------------------
// One feature: the bounded generate -> validate -> feedback loop.
// ---------------------------------------------------------------------------
function buildAndScore(ctx, feature) {
  let feedback = null; // weakest-criterion note fed back into the next build

  for (let round = 1; round <= MAX_ROUNDS; round++) {
    // --- STEP 3: BUILD (generate skill / Builder role) -----------------------
    // First round builds from spec only; later rounds receive the Evaluator's
    // weakest-criterion feedback so the rebuild targets the actual deficit.
    const built = agent('generate', {
      // The Builder reads the spec + docs/UI_DESIGN.md (see the skill).
      skill: '.claude/skills/generate/SKILL.md',
      feature, // { id, name, description, dependencies, ... }
      round,
      feedback, // null on round 1; { criterion, score, note } on rebuilds
      app: APP,
      prompt:
        `Build feature ${feature.id} ("${feature.name}") per its acceptance ` +
        `criteria in ${FEATURE_LIST} and docs/UI_DESIGN.md.` +
        (feedback
          ? ` REBUILD round ${round}: the Evaluator scored "${feedback.criterion}" ` +
            `lowest (${feedback.score}). Focus this pass on raising that ` +
            `criterion: ${feedback.note}`
          : ` Initial build (round ${round}).`),
    });

    // --- STEP 4: VALIDATE (browser-validate skill / Evaluator role) ----------
    // Playwright-drives the running app and scores the 4 criteria, writing the
    // scores into docs/EVALUATION.md (the scoring source of truth).
    const review = agent('browser-validate', {
      skill: '.claude/skills/browser-validate/SKILL.md',
      feature,
      build: built,
      app: APP, // Evaluator launches APP.frontend/APP.backend, opens APP.url
      criteria: CRITERIA,
      threshold: PASS_THRESHOLD,
      prompt:
        `Validate feature ${feature.id} in the running app at ${APP.url}. ` +
        `Score each of [${CRITERIA.join(', ')}] 0-10 per docs/EVALUATION.md, ` +
        `record the scores there, and return { scores, weakest, passed }.`,
    });

    // review.passed === true means EVERY criterion met PASS_THRESHOLD.
    if (review.passed) {
      ctx.markFeature(feature.id, 'passed', review); // updates feature_list.json
      ctx.note(`progress.md`, `${feature.id} passed in round ${round}.`);
      return review;
    }

    // --- STEP 5: FEEDBACK -> REBUILD ----------------------------------------
    // Feed ONLY the single weakest criterion back to the Builder so the next
    // round has a clear, narrow target (per docs/ORCHESTRATION.md).
    feedback = review.weakest; // { criterion, score, note }
  }

  // Budget exhausted without passing: stop the bounded loop and flag for a
  // human. Do NOT loop forever — the loop is intentionally bounded.
  ctx.markFeature(feature.id, 'needs-human', { rounds: MAX_ROUNDS, feedback });
  ctx.note(
    'progress.md',
    `${feature.id} did NOT pass after ${MAX_ROUNDS} rounds; weakest left: ` +
      `${feedback ? feedback.criterion : 'n/a'}. Needs human review.`,
  );
  return { passed: false, feature: feature.id, feedback };
}
