import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { motion } from "framer-motion";
import { Pencil, Trash2, Inbox } from "lucide-react";

import { Button } from "./ui/button";
import { EmptyState } from "./ui/empty-state";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";

type EntityTableProps<T extends { id: number }> = {
  columns: ColumnDef<T>[];
  data: T[];
  onEdit: (row: T) => void;
  onDelete?: (id: number) => void;
  /** Gate the Edit action per row (default: always allowed). */
  canModify?: (row: T) => boolean;
  /** Gate the destructive action per row (default: same as canModify). */
  canDelete?: (row: T) => boolean;
  destructiveLabel?: string;
  confirmText?: string;
};

export function EntityTable<T extends { id: number }>({
  columns,
  data,
  onEdit,
  onDelete,
  canModify = () => true,
  canDelete,
  destructiveLabel = "Delete",
  confirmText = "Delete this record?",
}: EntityTableProps<T>) {
  const canRemove = canDelete ?? canModify;
  const table = useReactTable({
    data,
    columns: [
      ...columns,
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex min-w-max justify-end gap-2">
            <Button variant="outline" className="h-8 px-3" disabled={!canModify(row.original)} onClick={() => onEdit(row.original)}>
              <Pencil className="h-3.5 w-3.5" />
              Edit
            </Button>
            {onDelete && (
              <Button
                variant="danger"
                className="h-8 px-3"
                disabled={!canRemove(row.original)}
                onClick={() => {
                  if (window.confirm(confirmText)) {
                    onDelete(row.original.id);
                  }
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
                {destructiveLabel}
              </Button>
            )}
          </div>
        ),
      },
    ],
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="surface-card min-w-0 overflow-hidden">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <TableHead key={header.id}>
                  {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.map((row) => (
            <motion.tr
              key={row.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16, delay: row.index * 0.025 }}
              className="transition-colors hover:bg-muted/50"
            >
              {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
              ))}
            </motion.tr>
          ))}
          {!data.length && (
            <TableRow>
              <TableCell colSpan={columns.length + 1} className="p-6">
                <EmptyState icon={Inbox} title="No records yet" message="Create the first entry and it will appear here." />
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
