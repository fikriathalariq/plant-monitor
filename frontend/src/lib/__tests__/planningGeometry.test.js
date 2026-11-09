import test from 'node:test';
import assert from 'node:assert/strict';

import {
  SHIFT_MINUTES,
  GRID_MINUTES,
  minutesToPct,
  pctToMinutes,
  snapToGrid,
  clamp,
  batchTotalDuration,
  rangesOverlap,
  hasOverlap,
  splitDefaultPhases,
  createRunningBlock,
  computeSteamTimeline,
  offsetToClockLabel,
  clockLabelToOffset,
  planFromApi,
  planToPayload,
  detectModeMismatches,
} from '../planningGeometry.js';

import {
  PHASE_COLORS,
  STATUS_TILE,
  STATUS_LEGEND,
  AVAILABILITY_PHASE,
} from '../phaseColors.js';

test('minutesToPct and pctToMinutes bi-directional conversion', () => {
  assert.equal(minutesToPct(0), 0);
  assert.equal(minutesToPct(720), 50);
  assert.equal(minutesToPct(1440), 100);

  assert.equal(pctToMinutes(0), 0);
  assert.equal(pctToMinutes(50), 720);
  assert.equal(pctToMinutes(100), 1440);
});

test('snapToGrid and clamp utilities', () => {
  assert.equal(snapToGrid(0), 0);
  assert.equal(snapToGrid(7), 0);
  assert.equal(snapToGrid(8), 15);
  assert.equal(snapToGrid(22), 15);
  assert.equal(snapToGrid(23), 30);
  assert.equal(snapToGrid(-10), 0);

  assert.equal(clamp(5, 0, 10), 5);
  assert.equal(clamp(-3, 0, 10), 0);
  assert.equal(clamp(15, 0, 10), 10);
});

test('batchTotalDuration aggregates block durationMinutes', () => {
  const batch = {
    blocks: [
      { phase: 'HEAT', durationMinutes: 30 },
      { phase: 'STEADY', durationMinutes: 60 },
      { phase: 'COOL', durationMinutes: 30 },
    ],
  };
  assert.equal(batchTotalDuration(batch), 120);
  assert.equal(batchTotalDuration({}), 0);
});

test('rangesOverlap and hasOverlap detect collisions correctly', () => {
  assert.equal(rangesOverlap(0, 60, 60, 120), false);
  assert.equal(rangesOverlap(0, 60, 30, 90), true);
  assert.equal(rangesOverlap(30, 90, 0, 60), true);

  const existingBatches = [
    {
      clientId: 'batch_1',
      startOffsetMinutes: 60,
      blocks: [{ phase: 'HEAT', durationMinutes: 120 }], // 60 -> 180
    },
  ];

  // Self should not collide
  assert.equal(hasOverlap(existingBatches, 'batch_1', 60, 120), false);
  // Overlapping candidate (120 to 240 overlaps 60-180)
  assert.equal(hasOverlap(existingBatches, 'batch_2', 120, 120), true);
  // Non-overlapping candidate (180 to 300)
  assert.equal(hasOverlap(existingBatches, 'batch_2', 180, 120), false);
});

test('splitDefaultPhases splits duration into HEAT, STEADY, COOL with grid snap', () => {
  const blocks = splitDefaultPhases(120); // 120 mins
  assert.equal(blocks.length, 3);
  assert.equal(blocks[0].phase, 'HEAT');
  assert.equal(blocks[1].phase, 'STEADY');
  assert.equal(blocks[2].phase, 'COOL');

  const total = blocks.reduce((acc, b) => acc + b.durationMinutes, 0);
  assert.equal(total, 120);
});

test('createRunningBlock produces single block for MANUAL machines', () => {
  const blocks = createRunningBlock(180);
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].phase, 'RUNNING');
  assert.equal(blocks[0].durationMinutes, 180);
});

test('clockLabelToOffset and offsetToClockLabel format 06:00-based shift time', () => {
  // Offset 0 = 06:00
  assert.equal(offsetToClockLabel(0), '06:00');
  // Offset 60 = 07:00
  assert.equal(offsetToClockLabel(60), '07:00');
  // Offset 1080 = 00:00 midnight
  assert.equal(offsetToClockLabel(1080), '00:00');

  // Inverse
  assert.equal(clockLabelToOffset('06:00'), 0);
  assert.equal(clockLabelToOffset('07:00'), 60);
  assert.equal(clockLabelToOffset('00:00'), 1080);
});

test('computeSteamTimeline backend parity check', () => {
  const batchesByMachine = {
    JD_01: [
      {
        startOffsetMinutes: 60,
        blocks: [
          { phase: 'HEAT', durationMinutes: 30 },
          { phase: 'STEADY', durationMinutes: 60 },
          { phase: 'COOL', durationMinutes: 30 },
        ],
      },
    ],
  };
  const machinesByCode = {
    JD_01: { average_steam_usage: 350.0, operation_mode: 'AUTO' },
  };

  const timeline = computeSteamTimeline(batchesByMachine, machinesByCode);
  assert.equal(timeline.values.length, SHIFT_MINUTES);
  assert.equal(timeline.max_kg_h, 350.0);
  assert.equal(timeline.unit, 'kg/h');

  // Minute 30 (before batch): 0 kg/h
  assert.equal(timeline.values[30], 0);
  // Minute 75 (HEAT): 350 kg/h
  assert.equal(timeline.values[75], 350);
  // Minute 100 (STEADY): 350 kg/h
  assert.equal(timeline.values[100], 350);
  // Minute 160 (COOL): 0 kg/h (COOL does not consume steam!)
  assert.equal(timeline.values[160], 0);
});

test('planFromApi and planToPayload continuation batch isolation', () => {
  const mockApiPlan = {
    id: 1,
    version: 2,
    shift_date: '2026-11-10',
    name: 'Plan Test',
    status: 'DRAFT',
    groups: [
      {
        machines: [
          {
            code: 'JD_01',
            batches: [
              {
                id: 10,
                label: 'Batch Fresh',
                start_offset_minutes: 0,
                is_continuation: false,
                blocks: [{ phase: 'HEAT', duration_minutes: 60 }],
              },
              {
                id: 11,
                label: 'Batch Continuation',
                start_offset_minutes: 0,
                is_continuation: true, // Overflow from yesterday!
                blocks: [{ phase: 'STEADY', duration_minutes: 60 }],
              },
            ],
          },
        ],
      },
    ],
  };

  const plan = planFromApi(mockApiPlan);
  assert.equal(plan.batchesByMachine.JD_01.length, 2);
  assert.equal(plan.batchesByMachine.JD_01[0].clientId, 'srv_10');
  assert.equal(plan.batchesByMachine.JD_01[1].clientId, 'cont_11');

  // planToPayload must exclude continuation batch so it does NOT duplicate in DB!
  const payload = planToPayload(plan, { JD_01: { operation_mode: 'AUTO' } });
  assert.equal(payload.batches.length, 1);
  assert.equal(payload.batches[0].label, 'Batch Fresh');
});

test('detectModeMismatches identifies AUTO vs MANUAL block discrepancy', () => {
  const batchesByMachine = {
    JD_01: [
      {
        // Has AUTO blocks (HEAT, STEADY, COOL) but machine is MANUAL
        blocks: [
          { phase: 'HEAT', durationMinutes: 30 },
          { phase: 'STEADY', durationMinutes: 60 },
          { phase: 'COOL', durationMinutes: 30 },
        ],
      },
    ],
  };
  const machinesByCode = {
    JD_01: { name: 'Jet Dyeing 01', operation_mode: 'MANUAL' },
  };

  const mismatches = detectModeMismatches(batchesByMachine, machinesByCode);
  assert.equal(mismatches.length, 1);
  assert.equal(mismatches[0].machineCode, 'JD_01');
  assert.equal(mismatches[0].fromMode, 'AUTO');
  assert.equal(mismatches[0].toMode, 'MANUAL');
});

test('phaseColors and statusTile dictionary validity', () => {
  assert.ok(PHASE_COLORS.HEAT);
  assert.ok(PHASE_COLORS.STEADY);
  assert.ok(PHASE_COLORS.COOL);
  assert.ok(PHASE_COLORS.RUNNING);
  assert.ok(PHASE_COLORS.NOSIGNAL);

  assert.equal(STATUS_TILE.HEAT.label, 'HEAT');
  assert.equal(STATUS_TILE.STEADY.label, 'KEEP');
  assert.equal(STATUS_TILE.COOL.label, 'COOL');
  assert.equal(STATUS_TILE.RUNNING.label, 'RUN');

  assert.ok(Array.isArray(STATUS_LEGEND));
  assert.ok(AVAILABILITY_PHASE.HEAT);
});
