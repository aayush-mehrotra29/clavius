// The Python simulation service needs persistent storage, native dependencies
// and background workers. This endpoint reports its absence without inventing
// flight results or treating a successful frontend deployment as a simulation.
export default {
  fetch() {
    return Response.json({
      status: 'backend_not_connected',
      detail: 'Live flight calculations and simulations are not connected on this hosted site. The lunar atlas (/app/atlas), VIPER visual driving and recorded replays (/app/drive) are available.',
    }, {status: 503, headers: {'Cache-Control': 'no-store'}});
  },
};
