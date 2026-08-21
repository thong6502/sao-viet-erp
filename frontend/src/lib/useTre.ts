/** `useTre` — bí danh tiếng Việt của `useDebounced`.
 *
 * Repo từng có HAI bản cùng một hook, chép tay giống nhau từng dòng: `lib/useTre.ts` (màn danh
 * mục · kỹ thuật máy) và `utils/useDebounced.ts` (màn thu mua · nội quy). Hai bản thì sớm muộn
 * lệch nhau một tham số mặc định, và không ai biết bản nào là bản đúng.
 *
 * Gộp về MỘT ruột ở `utils/useDebounced.ts`; giữ tên `useTre` vì 3 màn đang gọi theo tên đó, trong
 * đó 2 màn (Sửa chữa máy · Phiếu bảo trì) đang có việc sửa dở — đổi tên ở đó là giẫm lên nhau.
 */
export { useDebounced as useTre } from "../utils/useDebounced";
