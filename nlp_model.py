from gensim import corpora, models, matutils

model_path = '/DATA/luyao/model/'

class Model:
    def __init__(self, texts, save_id = None):
        self.save_id = save_id

        if save_id is not None:
            try:
                self.dictionary = corpora.Dictionary.load(model_path + '%s.dictionary' % save_id)
                self.tfidf = models.TfidfModel.load(model_path + '%s.tfidf' % save_id)
                print('model already exists!')
                return
            except:
                print('start init nlp model!')
                pass
        
        if (texts is None) or (texts == []):
            raise Exception('error on init nlp Model')
        
        self.dictionary = corpora.Dictionary(texts)
        
        corpus = [self.dictionary.doc2bow(text) for text in texts]
        
        self.tfidf = models.TfidfModel(corpus)

        # save model
        if save_id is not None:
            print('save model: ', save_id)
            self.dictionary.save(model_path + '%s.dictionary' % save_id)
            self.tfidf.save(model_path + '%s.tfidf' % save_id)


    def get_tfidf(self, tokens):
        query_bow = self.dictionary.doc2bow(tokens)
        query_tfidf = self.tfidf[query_bow]
        return query_tfidf


    def query_sim_tfidf(self, tokens1, tokens2):
        return matutils.cossim(self.get_tfidf(tokens1), self.get_tfidf(tokens2))


if __name__ == "__main__":
    documents = ["Shipment of gold damaged in a fire", "Delivery of silver arrived in a silver truck", "Shipment of gold arrived in a truck", "orz"]
    texts = [[word for word in document.lower().split()] for document in documents]
    m = Model(texts)
    print(m.query_sim_tfidf(['gold', 'in', 'shipment', 'shipment', 'orz'],['shipment', 'in', 'fire']))
