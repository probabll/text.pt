"""
All classes in this module manipulate generators, this means they *never* load the entire dataset to memory.
One exception is SentenceSplit(segmenter, read_n=-1),  see documentation below.

They all have the same API, generator comes in, generator comes out.
Generators (input or output) are assumed to yield a strings (e.g. a line in a file) whenever undergo next(...).

"""

from text.textprocessing import Pipeline, SentenceSegmenter


class Preprocess:

    def __init__(self, pipeline: Pipeline):
        self.pipeline = pipeline

    def __call__(self, generator):
        for line in generator:
            yield self.pipeline.pre(line.strip())


class Postprocess:

    def __init__(self, pipeline: Pipeline):
        self.pipeline = pipeline

    def __call__(self, generator):
        for line in generator:
            yield self.pipeline.post(line.strip())


class SentenceSplit:
    """
    Generator of sentence-segmented data.
    """

    def __init__(self, segmenter: SentenceSegmenter, read_n=1):
        """

        :param segmenter: a TextProcessingModule that segments strings into sentences.
        :param read_n: reads a number of lines and sends them all at once to the sentence segmenter.
            use -1 for all lines (WARNING: this means the whole data will be in memory!)
        """
        self.segmenter = segmenter
        self.read_n = read_n

    def __call__(self, generator):
        if self.read_n > 0:
            batch = []
            for line in generator:
                batch.append(line)
                if len(batch) >= self.read_n:
                    for sentence in self.segmenter.split(batch):
                        yield sentence
                    batch = []
            if len(batch) > 0:
                for sentence in self.segmenter.split(batch):
                    yield sentence
        else:
            for sentence in self.segmenter.split([line for line in generator]):
                yield sentence


class EnsureMaxLength:
    """
    This wrapper chops sentences enforcing a maximum length, but this is different from SentenceSplit
    * SentenceSplit uses punctuation to determine where to segment strings into sentences
        while EnsureMaxLength uses number of tokens alone.
    * SentenceSplit may produce sentences of arbitrary length
        while EnsureMaxLength will impose a constraint.

    EnsureMaxLength may discard sentences that are longer than the maximum allowed, if split=False, or
        it will chop them at the maximum sentence length and chain the parts in sequence.
        The class also provides a mechanism to join the parts back together.
    """

    def __init__(self, max_length=-1, split=False):
        """

        :param max_length: longest sentence allowed (in number of tokens as produce by string.split()),
            use -1 for no maximum
        :param split: by default (False) we discard long sentences,
            if you switch this to True, then long sentences will be chopped, the parts will be yielded
            in sequence and you can count on self.join to regroup them.
        """
        self.max_length = max_length
        self.split = split
        self.nb_parts = []

    @staticmethod
    def split_list(x, size):
        output = []
        if size < 0:
            return [x]
        elif size == 0:
            raise ValueError("Use size -1 for no splitting or size more than 0.")
        while True:
            if len(x) > size:
                output.append(x[:size])
                x = x[size:]
            else:
                output.append(x)
                break
        return output

    def __call__(self, generator):
        if self.max_length < 0:
            yield from generator
        for line in generator:
            line = line.strip()  # strip \n
            tokens = line.split()
            if len(tokens) <= self.max_length:
                # it's important to update nb_parts before yielding (not to break 'join')
                self.nb_parts.append(1)
                yield line
            elif self.split:  # sentence splitting (saves metadata to restore line-alignment with input)
                parts = EnsureMaxLength.split_list(tokens, self.max_length)
                # it's important to update nb_parts before yielding (not to break 'join')
                self.nb_parts.append(len(parts))
                for part in parts:
                    yield ' '.join(part)

    def join(self, generator):
        if self.max_length < 0 or not self.split:
            yield from generator
        else:
            # This is important: note that perhaps the generator hasn't yet generated nb_parts
            # thus we cannot iterate over nb_parts
            # we should rather get a line from the generator and maintain an index
            i = 0
            parts = []
            for line in generator:
                parts.append(line)
                if len(parts) == self.nb_parts[i]:
                    i += 1
                    yield ' '.join(parts)
                    parts = []