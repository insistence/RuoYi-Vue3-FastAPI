import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
const fixtures = JSON.parse(readFileSync(new URL('./fixtures.json', import.meta.url)))

/**
 * 为 Web、App 及 Intl 兼容实现注册相同的时间契约测试。
 * 使用固定时间边界样例，不依赖本机配置、业务数据或预先生成的产物。
 *
 * @param {Object} time 待验证的时间工具模块
 * @returns {void}
 */
export function testTimeContract(time) {
  test('RFC 3339, invalid values, dates and explicit epoch units share one contract', () => {
    for (const { value, zone, display } of fixtures.instants) {
      time.setUserTimezone(zone)
      assert.equal(time.formatBusinessTime(value), display)
    }
    for (const value of fixtures.invalid) {
      assert.equal(time.formatBusinessTime(value), null, String(value))
    }
    for (const value of fixtures.epochs) {
      assert.equal(time.formatEpochSeconds(value), time.formatEpochMilliseconds(value * 1000))
    }
    assert.notEqual(time.formatEpochSeconds(999999999), time.formatEpochMilliseconds(999999999))
    assert.equal(time.normalizeRangeBoundary('2026-08-28'), '2026-08-28')
    assert.throws(() => time.normalizeRangeBoundary('2026-02-30'))
    assert.throws(() => time.setUserTimezone('Mars/Olympus'))
    time.setUserTimezone(' Asia/Shanghai ')
    assert.equal(time.toRfc3339('2026-08-28 10:30:00'), '2026-08-28T10:30:00.000+08:00')
    assert.equal(time.toRfc3339('2026-08-28T10:30:00.123456+08:00'), '2026-08-28T10:30:00.123+08:00')
  })

  test('gap is rejected and both fold occurrences require an explicit choice', async () => {
    time.setUserTimezone('America/New_York')
    assert.throws(() => time.toRfc3339('2026-03-08 02:30:00'), { code: 'DST_GAP' })
    assert.throws(() => time.toRfc3339('2026-11-01 01:30:00'), { code: 'DST_FOLD' })
    assert.deepEqual(
      time.getWallTimeCandidates('2026-11-01 01:30:00').map(item => item.offset),
      ['-04:00', '-05:00']
    )
    assert.equal(time.toRfc3339('2026-11-01 01:30:00', { offset: '-05:00' }), '2026-11-01T01:30:00.000-05:00')
    const input = { scheduledAt: '2026-11-01 01:30:00' }
    const result = await time.resolveTimeFields(input, ['scheduledAt'], async () => '-04:00')
    assert.equal(result.scheduledAt, '2026-11-01T01:30:00.000-04:00')
    assert.equal(input.scheduledAt, '2026-11-01 01:30:00')
    assert.equal(time.getWallTimeCandidates('2026-04-05 01:45:00', 'Australia/Lord_Howe').length, 2)
  })

  test('unchanged form and subrows preserve milliseconds, original fold, null and omission', () => {
    time.setUserTimezone('America/New_York')
    const original = { id: 7, birthday: '2000-02-29', at: '2026-11-01T01:30:00.456-05:00', blank: null }
    const form = time.prepareTimeFields(original, ['at', 'blank', 'missing'])
    assert.equal(form.at, '2026-11-01 01:30:00')
    time.setUserTimezone('Asia/Shanghai') // 已打开的表单保留原时区，重新打开时再使用新时区。
    assert.equal(time.getTimeFieldsTimezone(form), 'America/New_York')
    assert.deepEqual(time.serializeTimeFields(form, ['at', 'blank', 'missing']), original)
    form.at = '2026-11-02 01:30:00'
    assert.equal(time.serializeTimeFields(form, ['at']).at, '2026-11-02T01:30:00.000-05:00')
    form.at = ''
    assert.equal(time.serializeTimeFields(form, ['at']).at, null)
    const rows = [original, { id: 8, at: null }, { id: 9 }].map(row => time.prepareTimeFields(row, ['at']))
    assert.deepEqual(
      rows.map(row => time.serializeTimeFields(row, ['at'])),
      [original, { id: 8, at: null }, { id: 9 }]
    )
  })

  test('account timezone follows device changes, supports manual override and preserves business timezone', () => {
    const DateTimeFormat = Intl.DateTimeFormat
    let deviceZone = 'America/New_York'
    try {
      Intl.DateTimeFormat = function (locale, options) {
        return new DateTimeFormat(locale, options || { timeZone: deviceZone })
      }
      time.setBusinessTimezone('Asia/Shanghai')
      time.setUserTimezone('auto')
      assert.equal(time.getUserTimezone(), 'auto')
      assert.equal(time.getDisplayTimezone(), 'America/New_York')
      const instant = '2026-08-28T02:30:00.000Z'
      assert.equal(time.formatBusinessTime(instant), '2026-08-27 22:30:00')
      deviceZone = 'Asia/Kathmandu'
      time.refreshDeviceTimezone()
      assert.equal(
        time.getDisplayTimezone(),
        new DateTimeFormat('en', { timeZone: 'Asia/Kathmandu' }).resolvedOptions().timeZone
      )
      assert.equal(time.formatBusinessTime(instant), '2026-08-28 08:15:00')
      assert.equal(time.toRfc3339('2026-08-28 08:15:00'), '2026-08-28T08:15:00.000+05:45')
      assert.equal(time.normalizeRangeBoundary('2000-02-29'), '2000-02-29')
      time.setUserTimezone('UTC')
      deviceZone = 'America/New_York'
      time.refreshDeviceTimezone()
      assert.equal(time.getDisplayTimezone(), 'UTC')
      assert.equal(time.getBusinessTimezone(), 'Asia/Shanghai')
      assert.equal(time.formatBusinessTime(instant), '2026-08-28 02:30:00')
      assert.equal(time.getSupportedTimezones(['UTC', 'Mars/Olympus']).includes('Mars/Olympus'), false)
      assert.throws(() => time.setUserTimezone('Mars/Olympus'))
      assert.equal(time.getUserTimezone(), 'UTC')
      // 兼容库的默认UTC不是设备时区；识别不可用时明确回退到系统配置。
      Intl.DateTimeFormat.polyfilled = true
      time.setUserTimezone('auto')
      assert.equal(time.getDeviceTimezone(), null)
      assert.equal(time.getDisplayTimezone(), 'Asia/Shanghai')
      time.setUserTimezone('America/New_York')
      assert.equal(time.getDisplayTimezone(), 'America/New_York')
    } finally {
      Intl.DateTimeFormat = DateTimeFormat
      time.setUserTimezone('auto')
    }
  })
}
