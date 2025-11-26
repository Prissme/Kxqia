export default {
  name: "messageCreate",
  execute(message) {
    const { slowMode } = message.client.security;
    slowMode.handleMessage(message);
  }
};
