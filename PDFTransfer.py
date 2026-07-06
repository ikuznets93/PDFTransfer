import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

# Пытаемся импортировать fitz (PyMuPDF)
try:
    import fitz
except ImportError:
    pass


def transfer_annotations_batch(source_pdf_path, target_dir_path):
    if not os.path.exists(source_pdf_path):
        raise FileNotFoundError("Исходный файл с пометками не найден.")
    if not os.path.exists(target_dir_path):
        raise FileNotFoundError("Целевая папка не найдена.")

    pdf_files = [
        f
        for f in os.listdir(target_dir_path)
        if f.lower().endswith(".pdf")
        and os.path.abspath(os.path.join(target_dir_path, f))
        != os.path.abspath(source_pdf_path)
    ]

    if not pdf_files:
        return "В выбранной папке не найдено других PDF-файлов для обработки."

    output_dir = os.path.join(target_dir_path, "processed_with_notes")
    os.makedirs(output_dir, exist_ok=True)

    success_count = 0
    errors = []

    for file_name in pdf_files:
        src_doc = None
        tgt_doc = None
        try:
            target_path = os.path.join(target_dir_path, file_name)
            output_path = os.path.join(output_dir, file_name)

            src_doc = fitz.open(source_pdf_path)
            tgt_doc = fitz.open(target_path)

            total_pages = min(len(src_doc), len(tgt_doc))

            for page_num in range(total_pages):
                src_page = src_doc[page_num]
                tgt_page = tgt_doc[page_num]

                for annot in src_page.annots():
                    # Определяем числовой тип аннотации (например, 4 для Square, 8 для Highlight)
                    annot_type_num = annot.type[0]
                    rect = annot.rect

                    # Подбираем правильный метод создания в зависимости от типа
                    new_annot = None
                    try:
                        if annot_type_num == 0:  # Text / Sticky Note
                            new_annot = tgt_page.add_text_annot(rect.tl)
                        
                        elif (
                            annot_type_num == 2
                        ):  # FreeText (Текстовые блоки / Печатный текст)
                            text_content = (
                                annot.info.get("content", "")
                                if annot.info
                                else ""
                            )

                            # Узнаем поворот страницы
                            page_rotation = tgt_page.rotation

                            # Создаем новый текстовый блок
                            new_annot = tgt_page.add_freetext_annot(
                                rect, text_content
                            )

                            if new_annot:
                                # Исправляем поворот
                                if page_rotation != 0:
                                    try:
                                        new_annot.set_rotation(page_rotation)
                                    except:
                                        pass

                                # === ЖЕСТКИЙ ПЕРЕНОС ЦВЕТА И ШРИФТОВ ЧЕРЕЗ СЫРЫЕ PDF-КЛЮЧИ ===
                                try:
                                    # Получаем доступ к низкоуровневым PDF-объектам (словарям)
                                    src_obj = src_page.doc.xref_object(
                                        annot.xref, compacted=True
                                    )

                                    # В PDF цвет текста и параметры шрифта живут в строке /DA (Default Appearance)
                                    # Пример: "0 0 1 rg /Helvetica 12 Tf" (где 0 0 1 - это синий цвет)
                                    if "/DA" in src_obj:
                                        # Извлекаем сырую строку DA из старого файла
                                        raw_da = src_page.doc.xref_get_key(
                                            annot.xref, "DA"
                                        )[1]
                                        if raw_da:
                                            # Записываем ее напрямую в новый файл, минуя высокоуровневые методы
                                            new_annot.set_da(
                                                raw_da.strip("() ")
                                            )

                                    # На всякий случай копируем /C (цвет рамки) и /IC (цвет заливки фона)
                                    if "/C" in src_obj:
                                        raw_c = src_page.doc.xref_get_key(
                                            annot.xref, "C"
                                        )[1]
                                        if raw_c:
                                            new_annot.parent.doc.xref_set_key(
                                                new_annot.xref, "C", raw_c
                                            )

                                    if "/IC" in src_obj:
                                        raw_ic = src_page.doc.xref_get_key(
                                            annot.xref, "IC"
                                        )[1]
                                        if raw_ic:
                                            new_annot.parent.doc.xref_set_key(
                                                new_annot.xref, "IC", raw_ic
                                            )

                                except Exception as raw_err:
                                    # Если низкоуровневый разбор не удался, откатываемся на стандартные методы
                                    try:
                                        da_string = (
                                            annot.parent.load_annot(annot.xref)
                                            ._get_compiled_DA()
                                        )
                                        if da_string:
                                            new_annot.set_da(da_string)
                                    except:
                                        pass
                        elif annot_type_num == 3:  # Line
                            new_annot = tgt_page.add_line_annot(rect.tl, rect.br)
                        elif annot_type_num == 4:  # Square / Rect
                            new_annot = tgt_page.add_rect_annot(rect)
                        elif annot_type_num == 5:  # Circle
                            new_annot = tgt_page.add_circle_annot(rect)
                        elif annot_type_num == 6:  # Polygon
                            # Попробуем извлечь вершины, если нет - берем прямоугольник
                            vertices = annot.vertices if hasattr(annot, "vertices") else [rect.tl, rect.tr, rect.br, rect.bl]
                            new_annot = tgt_page.add_polygon_annot(vertices)
                        elif annot_type_num == 7:  # PolyLine
                            vertices = annot.vertices if hasattr(annot, "vertices") else [rect.tl, rect.br]
                            new_annot = tgt_page.add_polyline_annot(vertices)
                        elif annot_type_num == 8:  # Highlight
                            new_annot = tgt_page.add_highlight_annot(rect)
                        elif annot_type_num == 9:  # Underline
                            new_annot = tgt_page.add_underline_annot(rect)
                        elif annot_type_num == 11:  # StrikeOut
                            new_annot = tgt_page.add_strikeout_annot(rect)
                        elif annot_type_num == 12:  # RubberStamp
                            new_annot = tgt_page.add_stamp_annot(rect)
                        else:
                            # Для всех остальных редких типов используем универсальный резервный метод создания
                            # (В новых версиях MuPDF добавили общий метод под именем add_annot_with_type)
                            if hasattr(tgt_page, "add_annot_with_type"):
                                new_annot = tgt_page.add_annot_with_type(rect, annot_type_num)
                            elif hasattr(tgt_page, "add_annotation"):
                                new_annot = tgt_page.add_annotation(rect, annot_type_num)
                    except Exception as method_err:
                        # Если специфичный метод упал, пробуем создать базовый квадрат, чтобы сохранить текст комментария
                        try:
                            new_annot = tgt_page.add_rect_annot(rect)
                        except:
                            pass

                    # Если аннотацию удалось создать, копируем её свойства
                    if new_annot:
                        # Для текстовых блоков (тип 2) стандартный set_info вызывает ошибку,
                        # поэтому настраиваем метаданные выборочно или пропускаем
                        if annot_type_num != 2:
                            new_annot.set_info(annot.info)
                            if annot.colors:
                                new_annot.set_colors(annot.colors)
                            if annot.border:
                                new_annot.set_border(annot.border)
                        else:
                            # Для текстового блока копируем только автора и тему, если они есть,
                            # чтобы не вызвать ошибку 'Cannot be used for Free text'
                            try:
                                clean_info = {}
                                if "title" in annot.info:
                                    clean_info["title"] = annot.info["title"]
                                if "subject" in annot.info:
                                    clean_info["subject"] = annot.info[
                                        "subject"
                                    ]
                                new_annot.set_info(clean_info)
                            except:
                                pass

                        new_annot.update()

            tgt_doc.save(output_path, garbage=3, deflate=True)
            success_count += 1
        except Exception as e:
            errors.append(f"Ошибка в файле {file_name}: {str(e)}")
        finally:
            if tgt_doc: tgt_doc.close()
            if src_doc: src_doc.close()

    result_msg = f"Успешно обработано файлов: {success_count} из {len(pdf_files)}.\nРезультаты сохранены в папку 'processed_with_notes'."
    if errors:
        result_msg += "\n\nОшибки при обработке:\n" + "\n".join(errors)
    return result_msg


class PDFTransferGUI:

    def __init__(self, root):
        self.root = root
        self.root.title("Пакетный перенос пометок PDF")
        self.root.geometry("550x260")
        self.root.resizable(False, False)

        # Переменные для путей
        self.source_path = tk.StringVar()
        self.target_dir = tk.StringVar()

        # Интерфейс: Выбор исходного файла
        tk.Label(
            root, text="Файл с пометками (образец):", font=("Arial", 10, "bold")
        ).pack(anchor="w", padx=20, pady=(20, 2))
        frame1 = tk.Frame(root)
        frame1.pack(fill="x", padx=20)
        tk.Entry(
            frame1, textvariable=self.source_path, font=("Arial", 10)
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            frame1, text="Обзор...", bg="#e0e0e0", command=self.browse_file
        ).pack(side="right", padx=(10, 0))

        # Интерфейс: Выбор папки
        tk.Label(
            root,
            text="Папка с чистыми PDF (куда копировать):",
            font=("Arial", 10, "bold"),
        ).pack(anchor="w", padx=20, pady=(15, 2))
        frame2 = tk.Frame(root)
        frame2.pack(fill="x", padx=20)
        tk.Entry(
            frame2, textvariable=self.target_dir, font=("Arial", 10)
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            frame2, text="Обзор...", bg="#e0e0e0", command=self.browse_folder
        ).pack(side="right", padx=(10, 0))

        # Кнопка Запуска
        self.start_btn = tk.Button(
            root,
            text="ЗАПУСТИТЬ ПЕРЕНОС",
            font=("Arial", 11, "bold"),
            bg="#2e7d32",
            fg="white",
            command=self.start_process,
            height=2,
        )
        self.start_btn.pack(fill="x", padx=20, pady=30)

    def browse_file(self):
        filename = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if filename:
            self.source_path.set(filename)

    def browse_folder(self):
        directory = filedialog.askdirectory()
        if directory:
            self.target_dir.set(directory)

    def start_process(self):
        src = self.source_path.get().strip()
        tgt = self.target_dir.get().strip()

        if not src or not tgt:
            messagebox.showwarning(
                "Внимание",
                "Пожалуйста, выберите исходный файл и целевую папку.",
            )
            return

        self.start_btn.config(text="ОБРАБОТКА...", state="disabled")
        self.root.update_idletasks()

        try:
            summary = transfer_annotations_batch(src, tgt)
            messagebox.showinfo("Готово", summary)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Произошла ошибка: {str(e)}")
        finally:
            self.start_btn.config(text="ЗАПУСТИТЬ ПЕРЕНОС", state="normal")


if __name__ == "__main__":
    # Фикс размытых шрифтов на Windows при масштабировании экрана (DPI)
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass

    root = tk.Tk()
    app = PDFTransferGUI(root)
    root.mainloop()
