// @vitest-environment node
//
// Hidden tests for the "subscriptions after resetHandlers()" task.
// Everything goes through msw's public API (`setupServer`, `graphql.link`,
// `server.use`, `server.resetHandlers`) and a real `graphql-ws` client.
import { graphql } from 'msw/graphql'
import { setupServer } from 'msw/node'
import { createClient, type Client } from 'graphql-ws'

const ENDPOINT = 'http://localhost/graphql'
const WS_URL = 'ws://localhost/graphql'
const api = graphql.link(ENDPOINT)

const ON_TICK = 'subscription OnTick { tick }'
const ON_PING = 'subscription OnPing { ping }'

const server = setupServer()
const clients: Array<Client> = []

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'bypass' })
})

beforeEach(() => {
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(async () => {
  for (const client of clients.splice(0)) {
    await client.dispose()
  }
  server.resetHandlers()
  vi.restoreAllMocks()
})

afterAll(() => {
  server.close()
})

function tick(value: unknown) {
  return api.subscription('OnTick', ({ subscription }) => {
    subscription.publish({ data: { tick: value } })
  })
}

/** Open a client and wait until the connection is acknowledged. */
async function connect(): Promise<Client> {
  const client = createClient({ url: WS_URL, lazy: false, retryAttempts: 0 })
  clients.push(client)
  const connected = Promise.withResolvers<void>()
  client.on('connected', () => connected.resolve())
  client.on('error', (error) => connected.reject(error))
  await connected.promise
  return client
}

const UNHANDLED = Symbol('unhandled')

/**
 * Subscribe and return the first payload, or UNHANDLED when msw reports
 * the subscription as having no matching handler (it then sends nothing).
 */
async function firstResult(
  client: Client,
  query: string,
): Promise<unknown | typeof UNHANDLED> {
  const warnings = vi.mocked(console.warn).mock.calls.length
  const iterator = client.iterate({ query })
  let result: unknown = undefined
  let settled = false
  iterator.next().then((next) => {
    result = next.value
    settled = true
  })
  await vi.waitFor(
    () => {
      if (!settled && vi.mocked(console.warn).mock.calls.length === warnings) {
        throw new Error('still pending')
      }
    },
    { timeout: 3000, interval: 10 },
  )
  // Release the subscription either way.
  void iterator.return?.()
  return settled ? result : UNHANDLED
}

test('an initial handler keeps serving a connection opened before resetHandlers()', async () => {
  server.resetHandlers(tick(1))
  const client = await connect()

  server.resetHandlers()

  expect(await firstResult(client, ON_TICK)).toEqual({ data: { tick: 1 } })
})

test('an initial handler keeps serving after several resets', async () => {
  server.resetHandlers(tick('kept'))
  const client = await connect()

  server.resetHandlers()
  server.resetHandlers()
  expect(await firstResult(client, ON_TICK)).toEqual({ data: { tick: 'kept' } })

  server.resetHandlers()
  expect(await firstResult(client, ON_TICK)).toEqual({ data: { tick: 'kept' } })
})

test('a runtime handler stops serving a connection opened before resetHandlers()', async () => {
  server.resetHandlers(tick('initial'))
  server.use(tick('runtime'))
  const client = await connect()

  expect(await firstResult(client, ON_TICK)).toEqual({
    data: { tick: 'runtime' },
  })

  server.resetHandlers()

  expect(await firstResult(client, ON_TICK)).toEqual({
    data: { tick: 'initial' },
  })
})

test('a removed runtime handler is never called again', async () => {
  const runtimeResolver = vi.fn(({ subscription }) => {
    subscription.publish({ data: { tick: 'runtime' } })
  })
  server.resetHandlers(tick('initial'))
  server.use(api.subscription('OnTick', runtimeResolver))
  const client = await connect()
  await firstResult(client, ON_TICK)
  expect(runtimeResolver).toHaveBeenCalledTimes(1)

  server.resetHandlers()
  await firstResult(client, ON_TICK)
  await firstResult(client, ON_TICK)

  expect(runtimeResolver).toHaveBeenCalledTimes(1)
})

test('a runtime handler for another operation is removed too', async () => {
  server.resetHandlers(tick('initial'))
  server.use(
    api.subscription('OnPing', ({ subscription }) => {
      subscription.publish({ data: { ping: 'runtime' } })
    }),
  )
  const client = await connect()
  expect(await firstResult(client, ON_PING)).toEqual({
    data: { ping: 'runtime' },
  })

  server.resetHandlers()

  expect(await firstResult(client, ON_PING)).toBe(UNHANDLED)
  expect(await firstResult(client, ON_TICK)).toEqual({
    data: { tick: 'initial' },
  })
})

test('handlers replaced by resetHandlers(nextHandlers) stop serving open connections', async () => {
  server.resetHandlers(tick('old initial'))
  server.use(tick('old runtime'))
  const client = await connect()
  expect(await firstResult(client, ON_TICK)).toEqual({
    data: { tick: 'old runtime' },
  })

  server.resetHandlers(tick('new initial'))

  const result = await firstResult(client, ON_TICK)
  expect(result).not.toEqual({ data: { tick: 'old runtime' } })
  expect(result).not.toEqual({ data: { tick: 'old initial' } })

  // New connections use the new initial handler.
  const next = await connect()
  expect(await firstResult(next, ON_TICK)).toEqual({
    data: { tick: 'new initial' },
  })
})

test('a handler passed to resetHandlers() again keeps serving open connections', async () => {
  const shared = tick('shared')
  server.resetHandlers(shared)
  server.use(tick('runtime'))
  const client = await connect()

  server.resetHandlers(shared)

  expect(await firstResult(client, ON_TICK)).toEqual({
    data: { tick: 'shared' },
  })
})

test('the same handler instance can be used again in a later test', async () => {
  const reused = tick('reused')

  server.use(reused)
  const first = await connect()
  expect(await firstResult(first, ON_TICK)).toEqual({ data: { tick: 'reused' } })

  server.resetHandlers()

  server.use(reused)
  const second = await connect()
  expect(await firstResult(second, ON_TICK)).toEqual({
    data: { tick: 'reused' },
  })
})

test('a "once" initial handler can match again after resetHandlers()', async () => {
  server.resetHandlers(
    api.subscription(
      'OnTick',
      ({ subscription }) => {
        subscription.publish({ data: { tick: 'once' } })
      },
      { once: true },
    ),
  )
  const client = await connect()

  expect(await firstResult(client, ON_TICK)).toEqual({ data: { tick: 'once' } })
  expect(await firstResult(client, ON_TICK)).toBe(UNHANDLED)

  server.resetHandlers()

  expect(await firstResult(client, ON_TICK)).toEqual({ data: { tick: 'once' } })
})

test('handlers from two links to the same endpoint are kept and removed independently', async () => {
  const other = graphql.link(ENDPOINT)
  server.resetHandlers(
    api.subscription('OnTick', ({ subscription }) => {
      subscription.publish({ data: { tick: 'initial' } })
    }),
  )
  server.use(
    other.subscription('OnTick', ({ subscription }) => {
      subscription.publish({ data: { tick: 'other link' } })
    }),
  )
  const client = await connect()
  expect(await firstResult(client, ON_TICK)).toEqual({
    data: { tick: 'other link' },
  })

  server.resetHandlers()

  expect(await firstResult(client, ON_TICK)).toEqual({
    data: { tick: 'initial' },
  })
})

test('resetHandlers() still ends the active subscriptions and runs their cleanups', async () => {
  const cleanup = vi.fn()
  server.resetHandlers(
    api.subscription('OnTick', ({ subscription, finalize }) => {
      subscription.publish({ data: { tick: 1 } })
      finalize(cleanup)
    }),
  )
  const client = await connect()
  const iterator = client.iterate({ query: ON_TICK })
  await expect(iterator.next()).resolves.toEqual({
    done: false,
    value: { data: { tick: 1 } },
  })
  expect(cleanup).not.toHaveBeenCalled()

  server.resetHandlers()

  await vi.waitFor(() => expect(cleanup).toHaveBeenCalledTimes(1))
  void iterator.return?.()
})

test('a handler added after resetHandlers() serves new connections', async () => {
  server.resetHandlers(tick('initial'))
  server.use(tick('first runtime'))
  await connect()
  server.resetHandlers()

  server.use(tick('second runtime'))
  const client = await connect()

  expect(await firstResult(client, ON_TICK)).toEqual({
    data: { tick: 'second runtime' },
  })
})
