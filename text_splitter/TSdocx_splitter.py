import docx
from typing import List
import re

class TSDocTextSplitter:
    def __init__(self, chunk_size=1250):
        self.headings = {}
        self.chunk_size = chunk_size

    def _is_heading_text(self, text: str) -> bool:
        """通过文本模式检测是否为标题/条款边界"""
        text = text.strip()
        if not text:
            return False
        # "第X条" "第X章" "第X节"
        if re.match(r'^(?:【[^】]*】)?\s*第[一二三四五六七八九十百千\d]+[条款章节]', text):
            return True
        # "一、" "二、" 等中文序号开头
        if re.match(r'^[一二三四五六七八九十]+[、）)]', text):
            return True
        # "（一）" "（二）" 等括号序号
        if re.match(r'^[（(][一二三四五六七八九十\d]+[）)]', text):
            return True
        # 短文本（<30字）可能是标题（如"第一章 总则"）
        if len(text) < 30 and not text.endswith(('。', '；', '，')):
            return True
        return False

    def _simple_split(self, text: str) -> List[str]:
        """简易递归切分"""
        if len(text) <= self.chunk_size:
            return [text] if text.strip() else []
        
        separators = ['。', '；', '，', '、']
        for sep in separators:
            if sep in text:
                parts = text.split(sep)
                result = []
                for part in parts:
                    result.extend(self._simple_split(part))
                return result
        
        return [text[i:i+self.chunk_size] for i in range(0, len(text), self.chunk_size)]

    def _split_by_headings(self, paragraphs, use_style=True) -> List[str]:
        """按标题/条款边界将段落分组"""
        groups = []
        current_heading = ''
        current_content = []
        
        for para in paragraphs:
            text = para.text.strip()
            if not text:
                continue
            
            is_heading = False
            if use_style and para.style.name.startswith('Heading'):
                is_heading = True
            elif self._is_heading_text(text):
                is_heading = True
            
            if is_heading:
                if current_content:
                    groups.append((current_heading, current_content))
                    current_heading = text
                    current_content = []
                else:
                    # 连续标题（如"第一章"后紧跟"第一条"），拼接标题前缀
                    current_heading = (current_heading + ' / ' + text) if current_heading else text
            else:
                current_content.append(text)
        
        # 最后一组
        if current_content:
            groups.append((current_heading, current_content))
        elif not groups and current_heading:
            # 只有标题没有内容的边界情况
            pass
        
        # 如果只有一组，说明标题检测失败，退回原始方式
        if len(groups) <= 1:
            return []
        
        # 切分各组内容
        result = []
        for heading, content in groups:
            content_text = '\n'.join(content)
            split_parts = self._simple_split(content_text)
            for part in split_parts:
                prefix = f"{heading}\n" if heading else ''
                result.append(prefix + part)
        
        return result

    def split_lines(self, lines: List[str]) -> List[str]:
        """通用文本行切分：对任意文本行列表做标题检测切分（不限 docx）"""
        # 包装为伪段落对象
        class FakePara:
            def __init__(self, text):
                self.text = text
                self.style = FakeStyle()
        class FakeStyle:
            name = 'Normal'
        
        fake_paras = [FakePara(line) for line in lines if line.strip()]
        result = self._split_by_headings(fake_paras, use_style=False)
        if not result:
            # 标题检测无果，按固定大小兜底
            all_text = '\n'.join(lines)
            result = self._simple_split(all_text)
        return result

    def split_text(self, doc: docx.document.Document) -> List[str]:
        paragraphs = list(doc.paragraphs)
        
        # 先尝试样式检测
        result = self._split_by_headings(paragraphs, use_style=True)
        if result:
            return result
        
        # 样式检测失败，回退到文本模式检测
        result = self._split_by_headings(paragraphs, use_style=False)
        if result:
            return result
        
        # 都失败，当做纯文本按固定大小切分
        all_text = '\n'.join(p.text for p in paragraphs if p.text.strip())
        return self._simple_split(all_text)
