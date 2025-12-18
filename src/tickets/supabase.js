import { createClient } from "@supabase/supabase-js";

let supabaseClient = null;

function buildClient() {
  if (supabaseClient) return supabaseClient;

  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_KEY;

  if (!url || !key) return null;

  supabaseClient = createClient(url, key, {
    auth: { autoRefreshToken: false, persistSession: false }
  });
  return supabaseClient;
}

export function getSupabase() {
  return buildClient();
}

export async function getOpenTicket(guildId, userId) {
  const client = buildClient();
  if (!client) return null;

  const { data, error } = await client
    .from("tickets")
    .select("*")
    .eq("guild_id", guildId)
    .eq("user_id", userId)
    .eq("status", "open")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) {
    console.error("Supabase getOpenTicket error", error);
    return null;
  }

  return data;
}

export async function getTicketByChannel(channelId) {
  const client = buildClient();
  if (!client) return null;

  const { data, error } = await client
    .from("tickets")
    .select("*")
    .eq("channel_id", channelId)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) {
    console.error("Supabase getTicketByChannel error", error);
    return null;
  }

  return data;
}

export async function createTicketRecord(ticket) {
  const client = buildClient();
  if (!client) return null;

  const payload = {
    guild_id: ticket.guildId,
    user_id: ticket.userId,
    channel_id: ticket.channelId,
    status: "open",
    topic: ticket.topic || null,
    created_at: new Date().toISOString()
  };

  const { data, error } = await client.from("tickets").insert(payload).select().maybeSingle();

  if (error) {
    console.error("Supabase createTicketRecord error", error);
    return null;
  }

  return data;
}

export async function closeTicketRecord(channelId, closedBy, status = "closed") {
  const client = buildClient();
  if (!client) return null;

  const { data, error } = await client
    .from("tickets")
    .update({ status, closed_by: closedBy, closed_at: new Date().toISOString() })
    .eq("channel_id", channelId)
    .select()
    .maybeSingle();

  if (error) {
    console.error("Supabase closeTicketRecord error", error);
    return null;
  }

  return data;
}
