"use client";

type Props = {
  title?: string;
  message: string;
  onRetry?: () => void;
};

export default function ErrorState({
  title = "Could not load data",
  message,
  onRetry,
}: Props) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      <p className="font-semibold">{title}</p>
      <p className="mt-1 break-words">{message}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-md border border-red-300 bg-white px-3 py-1.5 font-medium hover:bg-red-100"
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}
