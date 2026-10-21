import { test } from 'node:test'
import assert from 'node:assert/strict'
import { combinedScale, REGION_IDS } from '../static/js/net-salary-calc.js'

test('Madrid combined scale starts at 18% and tops out at 45%', () => {
  const { slices, foral, share } = combinedScale('madrid')
  assert.equal(foral, false)
  assert.equal(share, 1)
  assert.equal(slices[0].from, 0)
  assert.equal(slices.at(-1).to, null)
  assert.equal(slices[0].rate, 0.18)
  assert.equal(slices.at(-1).rate, 0.45)
})

test('slices are contiguous for every region', () => {
  for (const id of REGION_IDS) {
    const { slices } = combinedScale(id)
    for (let k = 1; k < slices.length; k++) assert.equal(slices[k].from, slices[k - 1].to, id)
  }
})

test('foral regions use their own scale only', () => {
  const { slices, foral } = combinedScale('navarra')
  assert.equal(foral, true)
  assert.equal(slices[0].rate, 0.13)
  assert.equal(slices[0].state, 0)
})

test('Ceuta pays 40% of the scale', () => {
  assert.equal(combinedScale('ceuta').share, 0.4)
})
