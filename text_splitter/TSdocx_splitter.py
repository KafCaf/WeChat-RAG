import docx
from typing import List

class TSDocTextSplitter:
    def __init__(self, chunk_size=1250):
        self.headings = {}
        self.chunk_size = chunk_size

    def _simple_split(self, text: str) -> List[str]:
        """简易递归切分，替代 langchain 的 RecursiveCharacterTextSplitter"""
        if len(text) <= self.chunk_size:
            return [text] if text.strip() else []
        
        # 按段落、句子、逗号、字符优先级切分
        separators = ['\n\n', '\n', '。', '；', '，', ' ']
        for sep in separators:
            if sep in text:
                parts = text.split(sep)
                result = []
                for part in parts:
                    result.extend(self._simple_split(part))
                return result
        
        # 兜底：按字符切
        return [text[i:i+self.chunk_size] for i in range(0, len(text), self.chunk_size)]

    def split_text(self, doc: docx.document.Document) -> List[str]:
        headings_content = []
        for para in doc.paragraphs:
            if para.style.name.startswith('Heading'):
                cur_heading_level = int(para.style.name.split()[-1])
                cur_heading = para.text
                self.headings[cur_heading_level] = cur_heading

                # 原始逻辑（可能在缺失中间层级标题时抛出 KeyError）
                # if cur_heading_level > 1:
                #     heading = ''
                #     for level in range(1, cur_heading_level):
                #         heading += '{last_heading}\n'.format(last_heading=self.headings[level])
                #     heading += cur_heading
                #     cur_heading = heading

                # 容错逻辑：如果某个上级标题不存在，则跳过该层级，避免 KeyError
                if cur_heading_level > 1:
                    heading = ''
                    for level in range(1, cur_heading_level):
                        last_heading = self.headings.get(level)
                        if last_heading:
                            heading += f"{last_heading}\n"
                    heading += cur_heading
                    cur_heading = heading

                headings_content.append((cur_heading, []))

            elif headings_content:
                headings_content[-1][1].append(para.text)
        
        split_headdings_content = []
        
        for heading, content in headings_content:
            split_content = self._simple_split('\n'.join(content))
            for c in split_content:
                split_headdings_content.append((heading, c))
        
        
        return self.concatenate_heading_content(split_headdings_content)

    def concatenate_heading_content(self, data):
        return [f"{heading}\n" + ''.join(content) for heading,content in data]