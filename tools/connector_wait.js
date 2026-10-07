// Bounded wait in Work Mode. A timeout cannot cancel an underlying MCP service.
// No retry here: the caller must persist UNKNOWN and reconcile its result.
async function boundedConnector(invoke, {waitMs = 25000} = {}) {
  if (!Number.isInteger(waitMs) || waitMs < 1 || waitMs > 60000) {
    throw new Error("INVALID_CONNECTOR_WAIT_LIMIT");
  }
  let timer;
  try {
    return await Promise.race([
      Promise.resolve().then(invoke).then(
        value => ({status: "RETURNED", value}),
        () => ({status: "UNKNOWN_CONNECTOR_ERROR"})
      ),
      new Promise(resolve => {
        timer = setTimeout(() => resolve({status: "UNKNOWN_WAIT_TIMEOUT"}), waitMs);
      })
    ]);
  } finally {
    clearTimeout(timer);
  }
}
