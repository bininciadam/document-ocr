import { afterEach, describe, expect, it, vi } from 'vitest'
import { LocalServer } from '../../packages/passport-ocr/src/local-server'

type ReadinessProbe = {
  _waitForReady(endpoint: string): Promise<string>
}

function readinessResponse(
  status: number,
  body: Record<string, unknown>,
): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('LocalServer readiness', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('waits through loading and resolves only when models are ready', async () => {
    vi.useFakeTimers()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(readinessResponse(503, { status: 'loading' }))
      .mockResolvedValueOnce(readinessResponse(200, { status: 'ready' }))
    vi.stubGlobal('fetch', fetchMock)
    const server = new LocalServer() as unknown as ReadinessProbe

    const readiness = server._waitForReady('http://127.0.0.1:9999')
    await vi.advanceTimersByTimeAsync(500)

    await expect(readiness).resolves.toBe('http://127.0.0.1:9999')
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock).toHaveBeenLastCalledWith(
      'http://127.0.0.1:9999/ready',
      expect.any(Object),
    )
  })

  it('fails immediately when configured model initialization failed', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      readinessResponse(503, {
        status: 'model_init_failed',
        error: 'MODEL_INIT_FAILED: unavailable model',
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const localServer = new LocalServer()
    const stopSpy = vi.spyOn(localServer, 'stop')
    const server = localServer as unknown as ReadinessProbe

    await expect(
      server._waitForReady('http://127.0.0.1:9999'),
    ).rejects.toThrow('MODEL_INIT_FAILED: unavailable model')
    expect(stopSpy).toHaveBeenCalledOnce()
    expect(fetchMock).toHaveBeenCalledOnce()
  })
})
