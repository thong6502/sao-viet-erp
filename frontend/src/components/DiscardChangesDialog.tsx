// Shared "unsaved changes" warning. Wraps ConfirmDialog with the standard wording so any
// form can guard closing while dirty — reuse instead of re-writing the copy each time.
import { ConfirmDialog } from "./ConfirmDialog";

interface DiscardChangesDialogProps {
  open: boolean;
  /** Leave without saving. */
  onDiscard: () => void;
  /** Stay in the form, keep the edits. */
  onKeepEditing: () => void;
  /** Optional override for the body text. */
  message?: string;
}

export function DiscardChangesDialog({
  open,
  onDiscard,
  onKeepEditing,
  message = "Bạn có thay đổi chưa lưu. Thoát mà không lưu?",
}: DiscardChangesDialogProps) {
  return (
    <ConfirmDialog
      open={open}
      title="Bỏ thay đổi?"
      message={message}
      confirmLabel="Thoát không lưu"
      cancelLabel="Tiếp tục sửa"
      danger
      onConfirm={onDiscard}
      onCancel={onKeepEditing}
    />
  );
}
