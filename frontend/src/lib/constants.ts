export const TOOL_OPTIONS = [
  { name: "message_fulfillment_team", label: "Message fulfillment team" },
  { name: "message_payments_team", label: "Message payments team" },
  { name: "message_logistics_team", label: "Message logistics team" },
  { name: "message_customer", label: "Message customer" },
  { name: "create_internal_note", label: "Create internal note" },
] as const;

export const EVENT_TYPES = [
  "payment_confirmed",
  "payment_failed",
  "shipment_created",
  "shipment_delayed",
  "delivered",
  "customer_message_received",
  "refund_requested",
] as const;

export const WORKFLOW_BLOCK_TYPES = [
  { value: "order_created", label: "Order created" },
  { value: "payment", label: "Payment" },
  { value: "shipment", label: "Shipment creation" },
  { value: "in_transit", label: "In transit / delays" },
  { value: "delivered", label: "Delivered" },
  { value: "post_delivery", label: "Post-delivery support" },
] as const;