export default {
  name: "messageCreate",
  execute(message) {
    const { slowMode, trap } = message.client.security;
    trap.handleMessage(message);
    slowMode.handleMessage(message);
  }
};
