FROM condaforge/miniforge3:25.3.1-0
RUN mkdir /repository
COPY environment.yml /environment.yml
RUN conda env create -f /environment.yml
RUN apt-get update && apt-get install -y curl unzip git
RUN	curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
RUN	unzip awscliv2.zip && ./aws/install
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
RUN useradd -ms /bin/bash auto
USER auto
ENTRYPOINT ["/entrypoint.sh"]